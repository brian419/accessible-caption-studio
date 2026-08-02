from pathlib import Path

from fastapi.testclient import TestClient

from accessible_caption_studio.models import CaptionCue, MediaAsset
from accessible_caption_studio.webapp import create_app


def seeded_client(tmp_path: Path) -> tuple[TestClient, str]:
    app = create_app(tmp_path / "storage")
    store = app.state.store
    project = store.create("API project")
    project.media = MediaAsset(
        filename="audio.wav", stored_name="audio.wav", duration=10, has_video=False, size_bytes=4
    )
    (store.project_dir(project.id) / "audio.wav").write_bytes(b"RIFF")
    project.cues = [CaptionCue(start=0, end=2, text="Hello")]
    store.save(project)
    return TestClient(app), project.id


def test_project_edit_validate_duplicate_and_delete(tmp_path: Path) -> None:
    client, project_id = seeded_client(tmp_path)
    response = client.patch(
        f"/api/projects/{project_id}",
        json={"name": "Renamed", "cues": [{"start": 0, "end": 2, "text": "Updated"}]},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    assert client.post(f"/api/projects/{project_id}/validate").status_code == 200
    duplicate = client.post(f"/api/projects/{project_id}/duplicate")
    assert duplicate.status_code == 201
    assert duplicate.json()["name"] == "Renamed copy"
    assert client.delete(f"/api/projects/{project_id}").status_code == 204
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_text_export_and_download(tmp_path: Path) -> None:
    client, project_id = seeded_client(tmp_path)
    export = client.post(f"/api/projects/{project_id}/exports/srt")
    assert export.status_code == 201
    filename = export.json()["filename"]
    download = client.get(f"/api/projects/{project_id}/exports/{filename}")
    assert download.status_code == 200
    assert "Hello" in download.text


def test_storage_cleanup_does_not_accept_projects(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)
    assert client.delete("/api/storage/projects").status_code == 400
    assert client.get("/api/storage").json()["project_count"] == 1


def test_token_is_write_only(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)
    assert (
        client.post("/api/settings/hugging-face-token", json={"token": "hf_private"}).status_code
        == 204
    )
    health = client.get("/api/health").json()
    assert health["hf_token_configured"] is True
    assert "hf_private" not in str(health)
