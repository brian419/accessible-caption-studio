import json
from pathlib import Path

from accessible_caption_studio.models import SpeakerTurn, WordToken
from accessible_caption_studio.visual import analyze_active_speakers, fuse_speaker_evidence


class FakeProgress:
    def __call__(self, *_args) -> None:
        pass

    def run_process(self, command):
        def sample(time, x, confidence):
            return {
                "time": time,
                "x": x,
                "y": 0,
                "width": 0.4,
                "height": 0.8,
                "active_confidence": confidence,
            }

        output = Path(command[-2])
        output.write_text(
            json.dumps(
                {
                    "engine": "test",
                    "tracks": [
                        {
                            "id": "face-1",
                            "identity_cluster_id": "Face identity 1",
                            "face_match_confidence": 0.95,
                            "samples": [
                                sample(0.1, 0, 0.95),
                                sample(0.5, 0, 0.9),
                                sample(1.5, 0, 0.05),
                            ],
                        },
                        {
                            "id": "face-2",
                            "identity_cluster_id": "Face identity 2",
                            "face_match_confidence": 0.94,
                            "samples": [
                                sample(0.1, 0.5, 0.05),
                                sample(1.3, 0.5, 0.9),
                                sample(1.7, 0.5, 0.95),
                            ],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return type("Result", (), {"returncode": 0, "stderr": "", "stdout": ""})()


def test_visual_evidence_can_split_two_active_faces_from_one_audio_label(tmp_path: Path) -> None:
    turns = [
        SpeakerTurn(speaker="Speaker 1", start=0, end=1, confidence=.55),
        SpeakerTurn(speaker="Speaker 1", start=1, end=2, confidence=.55),
    ]
    fused, tracks, status, summary = analyze_active_speakers(
        tmp_path / "video.mp4",
        tmp_path / "audio.wav",
        tmp_path / "models",
        tmp_path / "evidence.json",
        turns,
        FakeProgress(),
        expected_speaker_count=2,
        voice_cluster_count=1,
    )
    assert status == "complete"
    assert len(tracks) == 2
    assert [turn.speaker for turn in fused] == ["Speaker 1", "Speaker 2"]
    assert all(turn.method == "voice_face" for turn in fused)
    assert summary.voice_cluster_count == 1
    assert summary.face_identity_count == 2
    assert summary.final_speaker_count == 2


def test_two_face_identities_split_thirty_one_collapsed_voice_turns() -> None:
    turns = [
        SpeakerTurn(
            speaker="Speaker 1",
            start=index * 1.5,
            end=index * 1.5 + 1.2,
            confidence=0.72,
            audio_confidence=0.72,
            method="voice_only",
        )
        for index in range(31)
    ]
    tracks = []
    for index, turn in enumerate(turns):
        tracks.append(
            {
                "id": f"face-{index}",
                "identity_cluster_id": f"Face identity {(index % 2) + 1}",
                "face_match_confidence": 0.91,
                "samples": [
                    {
                        "time": turn.start + 0.3,
                        "active_confidence": 0.88,
                        "x": 0.1,
                        "y": 0.1,
                        "width": 0.3,
                        "height": 0.6,
                    }
                ],
            }
        )
    fused, _summaries, summary = fuse_speaker_evidence(
        turns, tracks, voice_cluster_count=1
    )
    assert {turn.speaker for turn in fused} == {"Speaker 1", "Speaker 2"}
    assert summary.voice_cluster_count == 1
    assert summary.face_identity_count == 2
    assert summary.final_speaker_count == 2


def test_exact_count_caps_independent_face_identities() -> None:
    turns = [
        SpeakerTurn(
            speaker="Speaker 1",
            start=index * 2,
            end=index * 2 + 1.5,
            confidence=0.7,
        )
        for index in range(6)
    ]
    tracks = [
        {
            "id": f"face-{index}",
            "identity_cluster_id": f"Face identity {(index % 3) + 1}",
            "face_match_confidence": 0.9,
            "samples": [
                {
                    "time": turn.start + 0.5,
                    "active_confidence": 0.9,
                    "x": 0.1,
                    "y": 0.1,
                    "width": 0.3,
                    "height": 0.6,
                }
            ],
        }
        for index, turn in enumerate(turns)
    ]
    fused, _summaries, summary = fuse_speaker_evidence(
        turns, tracks, expected_speaker_count=2, voice_cluster_count=1
    )
    assert len({turn.speaker for turn in fused}) <= 2
    assert summary.face_identity_count == 2
    assert summary.final_speaker_count <= 2


def test_word_level_faces_split_rapid_one_word_replies() -> None:
    words = [
        WordToken(text="Geez.", start=17.60, end=18.12, confidence=0.8),
        WordToken(text="What?", start=18.68, end=18.86, confidence=0.9),
    ]
    turns = [
        SpeakerTurn(speaker="Speaker 1", start=17.6, end=18.86, confidence=0.7)
    ]
    tracks = [
        {
            "id": "face-a",
            "identity_cluster_id": "Face identity 1",
            "face_match_confidence": 0.95,
            "samples": [
                {"time": 17.7, "active_confidence": 0.8},
                {"time": 18.0, "active_confidence": 0.8},
            ],
        },
        {
            "id": "face-b",
            "identity_cluster_id": "Face identity 2",
            "face_match_confidence": 0.95,
            "samples": [
                {"time": 18.68, "active_confidence": 0.8},
                {"time": 18.84, "active_confidence": 0.8},
            ],
        },
    ]
    fused, _summaries, summary = fuse_speaker_evidence(
        turns,
        tracks,
        expected_speaker_count=2,
        voice_cluster_count=1,
        words=words,
        camera_cuts=[18.52],
    )
    assert [(turn.speaker, turn.start, turn.end) for turn in fused] == [
        ("Speaker 1", 17.6, 18.12),
        ("Speaker 2", 18.68, 18.86),
    ]
    assert [word.speaker for word in words] == ["Speaker 1", "Speaker 2"]
    assert summary.final_speaker_count == 2


def test_one_frame_face_flicker_cannot_override_voice() -> None:
    words = [WordToken(text="word", start=1, end=1.2, confidence=0.9)]
    turns = [SpeakerTurn(speaker="Speaker 1", start=1, end=1.2, confidence=0.9)]
    tracks = [
        {
            "id": "flicker",
            "identity_cluster_id": "Face identity 2",
            "face_match_confidence": 0.9,
            "samples": [{"time": 1.1, "active_confidence": 0.99}],
        }
    ]
    fused, _summaries, _summary = fuse_speaker_evidence(
        turns, tracks, expected_speaker_count=2, voice_cluster_count=1, words=words
    )
    assert fused[0].speaker == "Speaker 1"
    assert fused[0].method == "voice_only"
