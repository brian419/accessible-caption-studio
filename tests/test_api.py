import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from accessible_caption_studio.models import CaptionCue, MediaAsset, SpeakerTurn, WordToken
from accessible_caption_studio.webapp import _reconcile_speaker_names, create_app


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


def test_speaker_display_names_are_saved_and_used_in_exports(tmp_path: Path) -> None:
    client, project_id = seeded_client(tmp_path)
    project = client.get(f"/api/projects/{project_id}").json()
    project["cues"][0]["speaker"] = "Speaker 1"
    response = client.patch(
        f"/api/projects/{project_id}",
        json={"cues": project["cues"], "speaker_names": {"Speaker 1": "Host"}},
    )
    assert response.status_code == 200
    exported = client.post(f"/api/projects/{project_id}/exports/srt").json()
    content = client.get(
        f"/api/projects/{project_id}/exports/{exported['filename']}"
    ).text
    assert "Host: Hello" in content
    assert response.json()["cues"][0]["speaker"] == "Speaker 1"


def test_speaker_names_only_survive_confident_reanalysis_matches() -> None:
    previous = [
        SpeakerTurn(speaker="Speaker 1", start=0, end=4, confidence=0.9),
        SpeakerTurn(speaker="Speaker 2", start=4, end=8, confidence=0.9),
    ]
    proposed = [
        SpeakerTurn(speaker="Speaker 2", start=0, end=4, confidence=0.9),
        SpeakerTurn(speaker="Speaker 1", start=4, end=5, confidence=0.5),
        SpeakerTurn(speaker="Speaker 2", start=5, end=8, confidence=0.5),
    ]
    names, warnings = _reconcile_speaker_names(
        {"Speaker 1": "Host", "Speaker 2": "Guest"}, previous, proposed
    )
    assert names == {"Speaker 2": "Host"}
    assert len(warnings) == 1
    assert "Guest" in warnings[0]


def test_speaker_evidence_endpoint_returns_only_requested_interval(tmp_path: Path) -> None:
    client, project_id = seeded_client(tmp_path)
    store = client.app.state.store
    (store.project_dir(project_id) / "speaker-evidence.json").write_text(
        json.dumps(
            {
                "tracks": [
                    {
                        "id": "face-1",
                        "speaker": "Speaker 1",
                        "samples": [
                            {"time": 1, "x": 0.1},
                            {"time": 9, "x": 0.2},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    evidence = client.get(
        f"/api/projects/{project_id}/speaker-evidence?start=0&end=3"
    )
    assert evidence.status_code == 200
    assert [sample["time"] for sample in evidence.json()["tracks"][0]["samples"]] == [1]


def test_storage_cleanup_does_not_accept_projects(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)
    assert client.delete("/api/storage/projects").status_code == 400
    assert client.get("/api/storage").json()["project_count"] == 1


def test_health_reports_token_free_speaker_engine(tmp_path: Path) -> None:
    client, _ = seeded_client(tmp_path)
    health = client.get("/api/health").json()
    assert health["speaker_engine"] == "local-ecapa"
    assert health["visual_speaker_engine"] == "sface-ecapa-v1"
    assert health["speaker_token_required"] is False


def test_overlap_analysis_returns_non_destructive_proposal(tmp_path: Path, monkeypatch) -> None:
    client, project_id = seeded_client(tmp_path)
    store = client.app.state.store
    (store.project_dir(project_id) / "analysis.wav").write_bytes(b"normalized")

    def fake_overlap(_self, _audio, start, _end, _references, progress):
        progress("Separating", 80, "Two tracks")
        return (
            [
                [WordToken(text="First voice", start=start, end=start + 1, confidence=0.9)],
                [WordToken(text="Second voice", start=start, end=start + 1, confidence=0.8)],
            ],
            ["Speaker 1", None],
        )

    monkeypatch.setattr(
        "accessible_caption_studio.analyzer.LocalAnalyzer.analyze_overlap", fake_overlap
    )
    response = client.post(
        f"/api/projects/{project_id}/analyze-overlap", json={"start": 0, "end": 2}
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    job = None
    for _ in range(100):
        job = client.get(f"/api/projects/{project_id}/jobs/{job_id}").json()
        if job["state"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert job and job["state"] == "completed"
    proposals = job["result"]["cues"]
    assert [cue["speaker"] for cue in proposals] == ["Speaker 1", "Speaker 2"]
    assert proposals[0]["overlap_group_id"] == proposals[1]["overlap_group_id"]
    assert client.get(f"/api/projects/{project_id}").json()["cues"][0]["text"] == "Hello"


def test_overlap_analysis_rejects_long_or_reversed_intervals(tmp_path: Path) -> None:
    client, project_id = seeded_client(tmp_path)
    assert (
        client.post(
            f"/api/projects/{project_id}/analyze-overlap", json={"start": 2, "end": 1}
        ).status_code
        == 400
    )
    assert (
        client.post(
            f"/api/projects/{project_id}/analyze-overlap", json={"start": 0, "end": 31}
        ).status_code
        == 400
    )


def test_cancelled_overlap_analysis_does_not_change_captions(tmp_path: Path, monkeypatch) -> None:
    client, project_id = seeded_client(tmp_path)
    store = client.app.state.store
    (store.project_dir(project_id) / "analysis.wav").write_bytes(b"normalized")

    def slow_overlap(_self, _audio, _start, _end, _references, progress):
        for percent in range(10, 90):
            progress("Separating", percent, "Working")
            time.sleep(0.005)
        raise AssertionError("cancel should interrupt through the progress callback")

    monkeypatch.setattr(
        "accessible_caption_studio.analyzer.LocalAnalyzer.analyze_overlap", slow_overlap
    )
    response = client.post(
        f"/api/projects/{project_id}/analyze-overlap", json={"start": 0, "end": 2}
    )
    job_id = response.json()["id"]
    assert client.post(f"/api/projects/{project_id}/jobs/{job_id}/cancel").status_code == 200
    job = None
    for _ in range(150):
        job = client.get(f"/api/projects/{project_id}/jobs/{job_id}").json()
        if job["state"] == "cancelled":
            break
        time.sleep(0.01)
    assert job and job["state"] == "cancelled"
    assert client.get(f"/api/projects/{project_id}").json()["cues"][0]["text"] == "Hello"


def _speaker_proposal(client: TestClient, project_id: str, monkeypatch) -> dict:
    store = client.app.state.store
    project = store.get(project_id)
    project.words = [
        WordToken(text="Reach", start=0, end=0.5, confidence=0.9),
        WordToken(text="out", start=0.5, end=1.0, confidence=0.9),
        WordToken(text="today.", start=1.0, end=1.4, confidence=0.9),
    ]
    project.cues = [
        CaptionCue(
            start=0,
            end=1,
            text="Reach out",
            speaker="Speaker 1",
            source="transcription",
        ),
        CaptionCue(
            start=1,
            end=1.4,
            text="today.",
            speaker="Speaker 9",
            source="transcription",
        ),
    ]
    store.save(project)
    (store.project_dir(project_id) / "analysis.wav").write_bytes(b"normalized")

    def fake_diarize(_self, _audio, _words, progress, expected_count):
        assert expected_count == 2
        progress("Finding speakers", 80, "Two voices")
        return [
            SpeakerTurn(speaker="Speaker 1", start=0, end=1.4, confidence=0.9),
            SpeakerTurn(speaker="Speaker 2", start=3, end=4, confidence=0.9),
        ]

    monkeypatch.setattr(
        "accessible_caption_studio.analyzer.LocalAnalyzer.diarize", fake_diarize
    )
    response = client.post(
        f"/api/projects/{project_id}/reanalyze-speakers",
        json={"expected_speaker_count": 2},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        job = client.get(f"/api/projects/{project_id}/jobs/{job_id}").json()
        if job["state"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert job["state"] == "completed"
    return job


def test_speaker_reanalysis_previews_then_atomically_applies(tmp_path: Path, monkeypatch) -> None:
    client, project_id = seeded_client(tmp_path)
    job = _speaker_proposal(client, project_id, monkeypatch)
    result = job["result"]
    assert result["detected_count"] == 2
    assert result["change_summary"]["joins"] == 1
    assert len(client.get(f"/api/projects/{project_id}").json()["cues"]) == 2

    applied = client.post(
        f"/api/projects/{project_id}/speaker-proposals/{job['id']}/apply"
    )
    assert applied.status_code == 200
    assert applied.json()["expected_speaker_count"] == 2
    assert [(cue["speaker"], cue["text"]) for cue in applied.json()["cues"]] == [
        ("Speaker 1", "Reach out today.")
    ]


def test_speaker_proposal_rejects_edits_made_after_preview(tmp_path: Path, monkeypatch) -> None:
    client, project_id = seeded_client(tmp_path)
    job = _speaker_proposal(client, project_id, monkeypatch)
    current = client.get(f"/api/projects/{project_id}").json()
    current["cues"][0]["text"] = "Edited after preview"
    assert client.patch(
        f"/api/projects/{project_id}", json={"cues": current["cues"]}
    ).status_code == 200
    response = client.post(
        f"/api/projects/{project_id}/speaker-proposals/{job['id']}/apply"
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "speaker_proposal_stale"


def test_transcript_repair_previews_and_applies_repeated_dialogue(
    tmp_path: Path, monkeypatch
) -> None:
    client, project_id = seeded_client(tmp_path)
    store = client.app.state.store
    project = store.get(project_id)
    project.words = [WordToken(text="Whatever.", start=0, end=0.8, confidence=0.9)]
    project.cues = [
        CaptionCue(
            start=0,
            end=0.8,
            text="Whatever.",
            speaker="Speaker 1",
            source="transcription",
        )
    ]
    store.save(project)
    (store.project_dir(project_id) / "analysis.wav").write_bytes(b"normalized")

    def fake_recovery(_self, _audio, words, progress, _cuts):
        progress("Recovering", 50, "Found repeated dialogue")
        return [
            *words,
            WordToken(
                text="Whatever.",
                start=2,
                end=2.8,
                confidence=0.9,
                transcription_source="recovery",
            ),
        ], {"inserted": 1, "replaced": 0, "discarded": 0, "regions": [[1.5, 3.0]]}

    def fake_diarize(_self, _audio, _words, _progress, _count):
        return [
            SpeakerTurn(speaker="Speaker 1", start=0, end=0.8, confidence=0.9),
            SpeakerTurn(speaker="Speaker 2", start=2, end=2.8, confidence=0.9),
        ]

    monkeypatch.setattr(
        "accessible_caption_studio.analyzer.LocalAnalyzer.recover_transcription",
        fake_recovery,
    )
    monkeypatch.setattr(
        "accessible_caption_studio.analyzer.LocalAnalyzer.diarize", fake_diarize
    )
    response = client.post(f"/api/projects/{project_id}/repair-transcript")
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        job = client.get(f"/api/projects/{project_id}/jobs/{job_id}").json()
        if job["state"] not in {"queued", "running"}:
            break
        time.sleep(0.01)
    assert job["state"] == "completed"
    assert len(client.get(f"/api/projects/{project_id}").json()["cues"]) == 1
    assert job["result"]["recovery_summary"]["inserted"] == 1

    applied = client.post(
        f"/api/projects/{project_id}/transcript-proposals/{job_id}/apply"
    )
    assert applied.status_code == 200
    assert [(cue["speaker"], cue["text"]) for cue in applied.json()["cues"]] == [
        ("Speaker 1", "Whatever."),
        ("Speaker 2", "Whatever."),
    ]
