from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from accessible_caption_studio.localization import (
    create_translation_track,
    translation_findings,
)
from accessible_caption_studio.migrations import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    migrate_project_payload,
)
from accessible_caption_studio.models import CaptionCue, CaptionTrack, MediaAsset, Project
from accessible_caption_studio.storage import ProjectStore
from accessible_caption_studio.webapp import create_app


def test_schema_v3_migrates_single_caption_list_into_original_track() -> None:
    payload = {
        "schema_version": 3,
        "id": "a" * 32,
        "name": "Legacy Spanish",
        "transcription_language": "es",
        "cues": [
            {
                "id": "b" * 32,
                "start": 0,
                "end": 2,
                "text": "Hola mundo",
                "source": "transcription",
            }
        ],
        "findings": [],
        "exports": [],
    }
    migrated, changed = migrate_project_payload(payload)
    assert changed is True
    assert migrated["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 4
    assert migrated["spoken_language"] == "es"
    assert len(migrated["caption_tracks"]) == 1
    assert migrated["caption_tracks"][0]["kind"] == "original"
    assert migrated["caption_tracks"][0]["language"] == "es"
    assert migrated["caption_tracks"][0]["cues"][0]["text"] == "Hola mundo"

    project = Project.model_validate(migrated)
    assert project.cues[0].text == "Hola mundo"
    assert project.active_caption_track().id == project.original_caption_track().id


def test_track_switching_keeps_edits_independent(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Localization")
    project.cues = [CaptionCue(start=0, end=2, text="Hello world")]
    store.save(project)
    original = project.original_caption_track()
    translated = CaptionTrack(
        language="es",
        kind="translation",
        source_track_id=original.id,
        source_language="en",
        cues=[CaptionCue(start=0, end=2, text="Hola mundo")],
    )
    project.caption_tracks.append(translated)
    project.activate_caption_track(translated.id)
    store.save(project)

    loaded = store.get(project.id)
    loaded.cues[0].text = "Hola, mundo editado"
    store.save(loaded)
    loaded.activate_caption_track(original.id)
    store.save(loaded)
    assert loaded.cues[0].text == "Hello world"

    loaded.activate_caption_track(translated.id)
    assert loaded.cues[0].text == "Hola, mundo editado"


def test_translation_qa_flags_changed_numbers_names_and_caption_rules() -> None:
    source = [CaptionCue(start=0, end=1, text="Yesterday Alice paid 42 dollars.")]
    translated = [CaptionCue(start=0, end=1, text="Ayer Alicia pagó 24 dólares adicionales rápidamente.")]
    findings = translation_findings(source, translated, "en", "es", 3)
    codes = {finding.code for finding in findings}
    assert "translation_number_changed" in codes
    assert "translation_name_changed" in codes
    assert "reading_speed" in codes


def test_create_translation_track_preserves_source_timing_and_cues(monkeypatch, tmp_path: Path) -> None:
    project = Project(name="Translated")
    project.spoken_language = "en"
    project.transcription_language = "en"
    project.cues = [
        CaptionCue(start=1, end=3, text="Hello", speaker="Speaker 1"),
        CaptionCue(start=4, end=6, text="Goodbye", speaker="Speaker 2"),
    ]
    project.sync_active_caption_track()

    monkeypatch.setattr(
        "accessible_caption_studio.localization.translate_texts_local",
        lambda texts, source_language, target_language, model_dir, progress=None: [
            "Hola",
            "Adiós",
        ],
    )
    track = create_translation_track(project, "es", tmp_path / "models")
    assert track.kind == "translation"
    assert track.language == "es"
    assert [cue.text for cue in track.cues] == ["Hola", "Adiós"]
    assert [(cue.start, cue.end) for cue in track.cues] == [(1, 3), (4, 6)]
    assert [cue.text for cue in project.original_caption_track().cues] == ["Hello", "Goodbye"]


def test_api_switch_edit_validate_and_export_tracks_independently(tmp_path: Path) -> None:
    app = create_app(tmp_path / "storage")
    store = app.state.store
    project = store.create("Track export")
    project.media = MediaAsset(
        filename="audio.wav",
        stored_name="audio.wav",
        duration=10,
        has_video=False,
    )
    project.cues = [CaptionCue(start=0, end=2, text="Hello world")]
    store.save(project)
    project = store.get(project.id)
    original = project.original_caption_track()
    translated = CaptionTrack(
        language="es",
        kind="translation",
        source_track_id=original.id,
        source_language="en",
        cues=[CaptionCue(start=0, end=2, text="Hola mundo")],
    )
    project.caption_tracks.append(translated)
    store.save(project)
    client = TestClient(app)

    activated = client.post(
        f"/api/projects/{project.id}/caption-tracks/{translated.id}/activate"
    )
    assert activated.status_code == 200
    assert activated.json()["cues"][0]["text"] == "Hola mundo"

    edited = client.patch(
        f"/api/projects/{project.id}",
        json={"cues": [{"id": translated.cues[0].id, "start": 0, "end": 2, "text": "Hola editado", "source": "manual"}]},
    )
    assert edited.status_code == 200
    validated = client.post(f"/api/projects/{project.id}/validate")
    assert validated.status_code == 200
    spanish_export = client.post(f"/api/projects/{project.id}/exports/srt")
    assert spanish_export.status_code == 201
    spanish_filename = spanish_export.json()["filename"]
    assert " - es - " in spanish_filename

    original_response = client.post(
        f"/api/projects/{project.id}/caption-tracks/{original.id}/activate"
    )
    assert original_response.status_code == 200
    assert original_response.json()["cues"][0]["text"] == "Hello world"
    english_export = client.post(f"/api/projects/{project.id}/exports/srt")
    assert english_export.status_code == 201
    english_filename = english_export.json()["filename"]
    assert " - en - " in english_filename
    assert english_filename != spanish_filename

    # An artifact from another track stays downloadable after switching tracks.
    assert client.get(
        f"/api/projects/{project.id}/exports/{spanish_filename}"
    ).status_code == 200


def test_translation_job_creates_track_without_real_model(monkeypatch, tmp_path: Path) -> None:
    app = create_app(tmp_path / "storage")
    store = app.state.store
    project = store.create("Translation job")
    project.cues = [CaptionCue(start=0, end=2, text="Hello")]
    store.save(project)
    monkeypatch.setattr(
        "accessible_caption_studio.localization.translate_texts_local",
        lambda texts, source_language, target_language, model_dir, progress=None: ["Hola"],
    )
    client = TestClient(app)
    response = client.post(
        f"/api/projects/{project.id}/caption-tracks/translations",
        json={"target_languages": ["es"]},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        job = app.state.jobs.get(project.id, job_id)
        if job.state.value not in {"queued", "running", "cancelling"}:
            break
        time.sleep(0.01)
    assert job.state.value == "completed"
    updated = store.get(project.id)
    spanish = updated.translation_caption_track("es")
    assert spanish is not None
    assert spanish.cues[0].text == "Hola"
    assert updated.original_caption_track().cues[0].text == "Hello"
