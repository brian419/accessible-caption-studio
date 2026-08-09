from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from accessible_caption_studio.exports import _render_items
from accessible_caption_studio.migrations import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    migrate_project_payload,
)
from accessible_caption_studio.models import CaptionCue, MediaAsset, Project
from accessible_caption_studio.storage import ProjectStore
from accessible_caption_studio.webapp import create_app


def _media(stored_name: str = "source.mp4") -> MediaAsset:
    return MediaAsset(
        filename=stored_name,
        stored_name=stored_name,
        content_type="video/mp4",
        duration=12.0,
        width=720,
        height=1280,
        has_video=True,
        has_audio=True,
        size_bytes=4,
    )


def _write_wave(path: Path, *, seconds: float = 1.0, sample_rate: int = 8000) -> None:
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        frames = bytearray()
        for index in range(int(seconds * sample_rate)):
            sample = int(math.sin(index / sample_rate * math.tau * 220) * 15000)
            frames.extend(struct.pack("<h", sample))
        target.writeframes(bytes(frames))


def test_schema_v1_migrates_favorite_and_cue_placement_defaults() -> None:
    project = Project(name="Schema one")
    payload = project.model_dump(mode="json")
    payload["schema_version"] = 1
    payload.pop("is_favorite", None)
    payload.pop("transcription_language", None)
    payload.pop("sdh_mode", None)
    payload["cues"] = [
        {
            "id": "a" * 32,
            "start": 0.0,
            "end": 2.0,
            "text": "Hello",
            "speaker": None,
            "source": "manual",
            "confidence": None,
            "sound_event_id": None,
            "overlap_group_id": None,
        }
    ]

    migrated, changed = migrate_project_payload(payload)

    assert changed is True
    assert migrated["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 3
    assert migrated["is_favorite"] is False
    assert migrated["transcription_language"] == "en"
    assert migrated["sdh_mode"] == "full"
    assert migrated["cues"][0]["position_override"] is None
    assert migrated["cues"][0]["alignment_override"] is None
    assert migrated["cues"][0]["vertical_margin_percent_override"] is None


def test_favorite_endpoint_does_not_change_project_edit_timestamp(tmp_path: Path) -> None:
    app = create_app(tmp_path / "storage")
    project = app.state.store.create("Favorite me")
    before = project.updated_at

    with TestClient(app) as client:
        response = client.post(
            f"/api/projects/{project.id}/favorite",
            json={"favorite": True},
        )

    assert response.status_code == 200
    saved = app.state.store.get(project.id)
    assert saved.is_favorite is True
    assert saved.updated_at == before


def test_persistent_revision_can_restore_an_earlier_caption_state(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Revision project")
    project.cues = [CaptionCue(start=0, end=2, text="Original caption")]
    store.save(project)
    checkpoint = store.create_revision(store.get(project.id), "Before edit")
    assert checkpoint is not None

    edited = store.get(project.id)
    edited.cues[0].text = "Changed caption"
    store.save(edited)

    revisions = store.list_revisions(project.id)
    assert revisions[0]["reason"] == "Before edit"

    restored = store.restore_revision(project.id, str(revisions[0]["id"]))
    assert restored.cues[0].text == "Original caption"
    assert len(store.list_revisions(project.id)) >= 2


def test_project_archive_round_trip_preserves_project_and_media(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Portable project")
    project.media = _media()
    project.is_favorite = True
    project.cues = [
        CaptionCue(
            start=1,
            end=3,
            text="Move me",
            position_override="top",
            alignment_override="left",
            vertical_margin_percent_override=8,
        )
    ]
    project.latest_job_id = "stale-job"
    media_path = store.project_dir(project.id) / project.media.stored_name
    media_path.write_bytes(b"test")
    store.save(project)
    store.create_revision(store.get(project.id), "Portable checkpoint")

    archive = store.create_archive(project.id)
    restored = store.restore_archive(archive)

    assert restored.id != project.id
    assert restored.name == "Portable project"
    assert restored.is_favorite is True
    assert restored.latest_job_id is None
    assert restored.cues[0].position_override == "top"
    assert restored.cues[0].alignment_override == "left"
    assert restored.cues[0].vertical_margin_percent_override == 8
    assert (store.project_dir(restored.id) / restored.media.stored_name).read_bytes() == b"test"
    assert store.list_revisions(restored.id)


def test_waveform_api_uses_existing_analysis_audio(tmp_path: Path) -> None:
    app = create_app(tmp_path / "storage")
    project = app.state.store.create("Waveform project")
    project.media = _media()
    (app.state.store.project_dir(project.id) / project.media.stored_name).write_bytes(b"test")
    _write_wave(app.state.store.project_dir(project.id) / "analysis.wav")
    app.state.store.save(project)

    with TestClient(app) as client:
        response = client.get(f"/api/projects/{project.id}/waveform")

    assert response.status_code == 200
    payload = response.json()
    assert payload["duration"] == 1.0
    assert len(payload["samples"]) > 0
    assert max(payload["samples"]) > 0.4


def test_render_items_apply_per_cue_placement_override() -> None:
    project = Project(name="Placement export")
    project.caption_style.position = "bottom"
    project.caption_style.alignment = "center"
    project.caption_style.vertical_margin_percent = 10
    project.cues = [
        CaptionCue(
            start=0,
            end=2,
            text="Top left",
            position_override="top",
            alignment_override="left",
            vertical_margin_percent_override=6,
        )
    ]

    rendered = _render_items(project)

    assert len(rendered) == 1
    style = rendered[0][3]
    assert style.position == "top"
    assert style.alignment == "left"
    assert style.vertical_margin_percent == 6
