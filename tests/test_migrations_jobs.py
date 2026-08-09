import json
from pathlib import Path

import pytest

from accessible_caption_studio.jobs import JobManager
from accessible_caption_studio.migrations import CURRENT_PROJECT_SCHEMA_VERSION
from accessible_caption_studio.models import AnalysisJob, JobState, Project
from accessible_caption_studio.storage import ProjectStore


def test_legacy_project_is_migrated_and_rewritten(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = Project(name="Legacy project")
    project_dir = store.project_dir(project.id)
    project_dir.mkdir(parents=True)
    (project_dir / "exports").mkdir()
    legacy_payload = project.model_dump(mode="json")
    legacy_payload.pop("schema_version", None)
    project_path = project_dir / "project.json"
    project_path.write_text(json.dumps(legacy_payload), encoding="utf-8")

    loaded = store.get(project.id)

    assert loaded.schema_version == CURRENT_PROJECT_SCHEMA_VERSION
    rewritten = json.loads(project_path.read_text(encoding="utf-8"))
    assert rewritten["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION


def test_future_project_schema_is_rejected(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Future project")
    project_path = store.project_dir(project.id) / "project.json"
    payload = json.loads(project_path.read_text(encoding="utf-8"))
    payload["schema_version"] = CURRENT_PROJECT_SCHEMA_VERSION + 1
    project_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="newer Accessible Caption Studio"):
        store.get(project.id)


def test_job_manager_marks_stale_active_jobs_interrupted(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Interrupted project")
    job = AnalysisJob(
        project_id=project.id,
        kind="analysis",
        state=JobState.RUNNING,
        stage="Transcribing",
        progress=42,
    )
    store.write_job(job)
    partial = store.project_dir(project.id) / "exports" / ".render.partial.mp4"
    partial.write_bytes(b"partial")
    render_temp = store.project_dir(project.id) / ".caption-render-stale"
    render_temp.mkdir()
    (render_temp / "caption.txt").write_text("partial", encoding="utf-8")

    manager = JobManager(store)
    recovered = store.read_job(project.id, job.id)

    assert job.id in manager.recovered_job_ids
    assert recovered.state == JobState.FAILED
    assert recovered.stage == "Interrupted"
    assert recovered.error_code == "job_interrupted"
    assert "Saved project data remains available" in recovered.message
    assert not partial.exists()
    assert not render_temp.exists()


def test_completed_jobs_are_not_changed_on_restart(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Complete project")
    job = AnalysisJob(
        project_id=project.id,
        kind="analysis",
        state=JobState.COMPLETED,
        stage="Complete",
        progress=100,
    )
    store.write_job(job)

    manager = JobManager(store)
    recovered = store.read_job(project.id, job.id)

    assert job.id not in manager.recovered_job_ids
    assert recovered.state == JobState.COMPLETED
    assert recovered.progress == 100
