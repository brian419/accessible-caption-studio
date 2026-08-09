from pathlib import Path

from fastapi.testclient import TestClient

from accessible_caption_studio.captions import parse_ttml_text, to_ttml
from accessible_caption_studio.migrations import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    migrate_project_payload,
)
from accessible_caption_studio.model_management import ModelManager
from accessible_caption_studio.models import AnalysisJob, CaptionCue, JobState, MediaAsset, Project
from accessible_caption_studio.reports import accessibility_report_html
from accessible_caption_studio.webapp import create_app


def test_ttml_round_trip_preserves_timing_and_text() -> None:
    cues = [
        CaptionCue(start=1.25, end=3.75, text="Hello there", speaker="Speaker 1"),
        CaptionCue(start=4, end=5.5, text="[music]", source="sound"),
    ]
    content = to_ttml(cues, "es")
    parsed = parse_ttml_text(content)
    assert len(parsed) == 2
    assert parsed[0].start == 1.25
    assert parsed[0].end == 3.75
    assert parsed[0].speaker == "Speaker 1"
    assert parsed[0].text == "Hello there"


def test_schema_v2_migrates_language_and_sdh_defaults() -> None:
    payload = {"schema_version": 2, "name": "Legacy", "cues": []}
    migrated, changed = migrate_project_payload(payload)
    assert changed is True
    assert migrated["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 4
    assert migrated["transcription_language"] == "en"
    assert migrated["sdh_mode"] == "full"


def test_authoring_report_contains_statistics_and_non_certification_notice() -> None:
    project = Project(name="Report project")
    project.media = MediaAsset(
        filename="video.mp4",
        stored_name="video.mp4",
        duration=10,
        width=320,
        height=180,
        has_video=True,
    )
    project.cues = [CaptionCue(start=0, end=2, text="Hello world")]
    report = accessibility_report_html(project)
    assert "Accessibility authoring report" in report
    assert "Timeline coverage" in report
    assert "not a legal certification" in report


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    app = create_app(tmp_path / "storage")
    project = app.state.store.create("Final batch")
    project.media = MediaAsset(
        filename="audio.wav", stored_name="audio.wav", duration=10, has_video=False
    )
    project.cues = [CaptionCue(start=0, end=2, text="Hello")]
    app.state.store.save(project)
    return TestClient(app), project.id


def test_project_preferences_and_new_exports(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)
    preferences = client.patch(
        f"/api/projects/{project_id}/preferences",
        json={"transcription_language": "es", "sdh_mode": "conservative"},
    )
    assert preferences.status_code == 200
    assert preferences.json()["transcription_language"] == "es"
    assert preferences.json()["sdh_mode"] == "conservative"
    for format_name in ("ttml", "report"):
        response = client.post(f"/api/projects/{project_id}/exports/{format_name}")
        assert response.status_code == 201
        filename = response.json()["filename"]
        downloaded = client.get(f"/api/projects/{project_id}/exports/{filename}")
        assert downloaded.status_code == 200
        assert downloaded.text


def test_overlap_retry_reuses_persisted_interval(tmp_path: Path) -> None:
    client, project_id = _client(tmp_path)
    store = client.app.state.store
    failed = AnalysisJob(
        project_id=project_id,
        kind="overlap-analysis",
        state=JobState.FAILED,
        parameters={"start": 1.0, "end": 2.0},
        error="interrupted",
    )
    store.write_job(failed)
    response = client.post(f"/api/projects/{project_id}/jobs/{failed.id}/retry")
    assert response.status_code == 202
    assert response.json()["kind"] == "overlap-analysis"
    assert response.json()["parameters"] == {"start": 1.0, "end": 2.0}


def test_model_manager_lists_individual_components(tmp_path: Path) -> None:
    manager = ModelManager(tmp_path / "models")
    rows = manager.list()
    ids = {row["id"] for row in rows}
    assert "whisper-en-accurate" in ids
    assert "whisper-multilingual-accurate" in ids
    assert "speaker-ecapa" in ids
    assert "sound-ast" in ids
    assert "face-yunet-sface" in ids
    assert "translation-m2m100" in ids
