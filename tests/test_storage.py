from pathlib import Path

import pytest

from accessible_caption_studio.models import CaptionCue, MediaAsset, Project
from accessible_caption_studio.storage import ProjectStore, safe_filename


def test_project_lifecycle_and_atomic_persistence(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("My project")
    project.cues = [CaptionCue(start=0, end=2, text="Hello")]
    store.save(project)
    assert store.get(project.id).cues[0].text == "Hello"
    assert store.list()[0].id == project.id
    assert not list(store.project_dir(project.id).glob("*.tmp"))
    store.delete(project.id)
    with pytest.raises(KeyError):
        store.get(project.id)


def test_existing_caption_json_defaults_to_no_overlap_group() -> None:
    cue = CaptionCue.model_validate({"start": 0, "end": 1, "text": "Legacy caption"})
    assert cue.overlap_group_id is None


def test_existing_project_defaults_to_automatic_speaker_count() -> None:
    project = Project.model_validate({"name": "Legacy project"})
    assert project.expected_speaker_count is None
    assert project.speaker_names == {}
    assert project.face_tracks == []
    assert project.visual_speaker_status == "not_analyzed"
    assert project.speaker_engine == "legacy_wavlm"
    assert project.fusion_summary.final_speaker_count == 0


def test_duplicate_copies_source_but_not_exports(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Original")
    source = store.project_dir(project.id) / "clip.mp4"
    source.write_bytes(b"media")
    project.media = MediaAsset(
        filename="clip.mp4", stored_name="clip.mp4", duration=2, has_video=True, size_bytes=5
    )
    store.save(project)
    duplicate = store.duplicate(project.id)
    assert duplicate.name == "Original copy"
    assert (store.project_dir(duplicate.id) / "clip.mp4").read_bytes() == b"media"
    assert duplicate.exports == []


def test_cache_cleanup_cannot_delete_projects(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Keep me")
    (store.models_dir / "model.bin").write_bytes(b"model")
    store.clear_cache("models")
    assert store.get(project.id).name == "Keep me"
    with pytest.raises(ValueError):
        store.clear_cache("projects")


def test_safe_names_strip_paths_and_markup() -> None:
    assert safe_filename("../../bad<script>.mp4") == "badscript.mp4"
