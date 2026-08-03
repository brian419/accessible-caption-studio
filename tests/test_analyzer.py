import json
from pathlib import Path
from types import SimpleNamespace

from accessible_caption_studio.analyzer import LocalAnalyzer
from accessible_caption_studio.errors import SetupError
from accessible_caption_studio.models import CaptionCue, SoundEvent, WordToken


def event(label: str, start: float, end: float, confidence: float) -> SoundEvent:
    return SoundEvent(label=label, start=start, end=end, confidence=confidence)


def test_merges_adjacent_duplicate_sound_windows() -> None:
    merged = LocalAnalyzer.merge_sounds(
        [event("applause", 0, 10, 0.6), event("applause", 5, 15, 0.8), event("music", 20, 30, 0.7)]
    )
    assert [(item.label, item.start, item.end) for item in merged] == [
        ("applause", 0, 15),
        ("music", 20, 30),
    ]
    assert merged[0].confidence == 0.8


def test_sound_cues_filter_weak_events_over_speech() -> None:
    speech = [CaptionCue(start=0, end=5, text="Talking")]
    events = [event("music", 0, 4, 0.4), event("alarm sounds", 5, 8, 0.8)]
    cues = LocalAnalyzer.sound_cues(events, speech)
    assert [cue.text for cue in cues] == ["[alarm sounds]"]


def test_accessible_sound_label_whitelist() -> None:
    assert LocalAnalyzer._accessible_label("Door, slam") == "door closes"
    assert LocalAnalyzer._accessible_label("Speech") is None


def test_whisper_runs_in_isolated_worker(tmp_path: Path, monkeypatch) -> None:
    captured: list[str] = []

    def fake_run(command, **_kwargs):
        captured.extend(command)
        Path(command[-1]).write_text(
            json.dumps([{"text": "Hello", "start": 0, "end": 0.5, "confidence": 0.9}]),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("accessible_caption_studio.analyzer.subprocess.run", fake_run)
    words = LocalAnalyzer(tmp_path / "models").transcribe(tmp_path / "audio.wav")
    assert words[0].text == "Hello"
    assert "accessible_caption_studio.whisper_worker" in captured


def test_optional_speaker_failure_keeps_transcription(tmp_path: Path, monkeypatch) -> None:
    analyzer = LocalAnalyzer(tmp_path / "models")
    monkeypatch.setattr(
        analyzer,
        "transcribe",
        lambda _path: [WordToken(text="Hello.", start=0, end=1, confidence=0.9)],
    )

    def unavailable_speakers(*_args):
        raise SetupError("diarization_failed", "Speaker model access is unavailable.")

    monkeypatch.setattr(analyzer, "diarize", unavailable_speakers)
    monkeypatch.setattr(analyzer, "detect_sounds", lambda _path: [])

    words, speakers, sounds, cues = analyzer.analyze(tmp_path / "audio.wav", lambda *_: None)

    assert words[0].text == "Hello."
    assert speakers == []
    assert sounds == []
    assert cues[0].text == "Hello."
    assert analyzer.warnings == [
        ("diarization_failed", "Speaker model access is unavailable.")
    ]


def test_speaker_windows_follow_pauses_and_limit_sample_length() -> None:
    words = [
        WordToken(text="One", start=0.0, end=0.7, confidence=0.9),
        WordToken(text="two", start=0.75, end=1.6, confidence=0.9),
        WordToken(text="Three", start=2.5, end=3.4, confidence=0.9),
        WordToken(text="four", start=3.45, end=4.3, confidence=0.9),
    ]
    assert LocalAnalyzer._speaker_windows(words) == [(0.0, 1.7), (2.4, 4.4)]


def test_speaker_embeddings_get_stable_anonymous_clusters() -> None:
    embeddings = [[1.0, 0.0], [0.98, 0.02], [0.0, 1.0], [0.03, 0.97], [1.0, 0.0]]
    assert LocalAnalyzer._cluster_speaker_embeddings(embeddings) == [0, 0, 1, 1, 0]
