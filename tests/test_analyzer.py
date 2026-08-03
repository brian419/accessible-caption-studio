import json
from pathlib import Path
from types import SimpleNamespace

from accessible_caption_studio.analyzer import LocalAnalyzer
from accessible_caption_studio.errors import SetupError
from accessible_caption_studio.models import CaptionCue, SoundEvent, SpeakerTurn, WordToken


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


def test_recovery_failure_keeps_every_primary_word(tmp_path: Path, monkeypatch) -> None:
    analyzer = LocalAnalyzer(tmp_path / "models")
    primary = [WordToken(text="Repeated", start=0, end=0.5, confidence=0.9)]
    monkeypatch.setattr(analyzer, "transcribe", lambda _path: primary)

    def failed_recovery(*_args):
        raise SetupError("transcript_recovery_failed", "Recovery unavailable")

    monkeypatch.setattr(analyzer, "recover_transcription", failed_recovery)
    monkeypatch.setattr(analyzer, "diarize", lambda *_args: [])
    monkeypatch.setattr(analyzer, "detect_sounds", lambda _path: [])
    words, _speakers, _sounds, cues = analyzer.analyze(
        tmp_path / "audio.wav", lambda *_args: None
    )
    assert words == primary
    assert [cue.text for cue in cues] == ["Repeated"]
    assert analyzer.warnings == [
        ("transcript_recovery_failed", "Recovery unavailable")
    ]


def test_analysis_splits_back_to_back_speakers_before_captioning(
    tmp_path: Path, monkeypatch
) -> None:
    analyzer = LocalAnalyzer(tmp_path / "models")
    words = [
        WordToken(text="Are", start=0, end=0.4, confidence=0.9),
        WordToken(text="you?", start=0.4, end=0.9, confidence=0.9),
        WordToken(text="Yes.", start=0.95, end=1.4, confidence=0.9),
    ]
    monkeypatch.setattr(analyzer, "transcribe", lambda _path: words)
    monkeypatch.setattr(
        analyzer,
        "diarize",
        lambda *_args: [
            SpeakerTurn(speaker="Speaker 1", start=0, end=0.92, confidence=0.9),
            SpeakerTurn(speaker="Speaker 2", start=0.92, end=1.5, confidence=0.9),
        ],
    )
    monkeypatch.setattr(analyzer, "detect_sounds", lambda _path: [])
    _words, _speakers, _sounds, cues = analyzer.analyze(
        tmp_path / "audio.wav", lambda *_args: None
    )
    assert [(cue.speaker, cue.text) for cue in cues] == [
        ("Speaker 1", "Are you?"),
        ("Speaker 2", "Yes."),
    ]


def test_speaker_windows_follow_pauses_and_limit_sample_length() -> None:
    words = [
        WordToken(text="One", start=0.0, end=0.7, confidence=0.9),
        WordToken(text="two", start=0.75, end=1.6, confidence=0.9),
        WordToken(text="Three", start=2.5, end=3.4, confidence=0.9),
        WordToken(text="four", start=3.45, end=4.3, confidence=0.9),
    ]
    assert LocalAnalyzer._speaker_windows(words) == [(0.0, 1.6), (2.5, 4.3)]


def test_brief_reply_still_creates_a_speaker_sample() -> None:
    words = [WordToken(text="Yes", start=1, end=1.4, confidence=0.9)]
    assert LocalAnalyzer._speaker_windows(words) == [(1.0, 1.4)]


def test_speaker_embeddings_get_stable_anonymous_clusters() -> None:
    embeddings = [[1.0, 0.0], [0.98, 0.02], [0.0, 1.0], [0.03, 0.97], [1.0, 0.0]]
    assert LocalAnalyzer._cluster_speaker_embeddings(embeddings) == [0, 0, 1, 1, 0]


def test_borderline_voices_no_longer_collapse_into_speaker_one() -> None:
    embeddings = [[1.0, 0.0], [0.78, 0.626]]
    assert LocalAnalyzer._cluster_speaker_embeddings(embeddings, expected_count=2) == [0, 1]


def test_speaker_confidence_is_high_for_distinct_clusters() -> None:
    confidence = LocalAnalyzer._speaker_confidences(
        [[1, 0], [0.99, 0.01], [0, 1], [0.01, 0.99]], [0, 0, 1, 1]
    )
    assert all(value > 0.9 for value in confidence)


def test_singleton_speaker_confidence_is_not_inflated() -> None:
    confidence = LocalAnalyzer._speaker_confidences([[1, 0], [0, 1]], [0, 1])
    assert all(value < 0.5 for value in confidence)


def test_auto_clustering_does_not_turn_short_samples_into_new_speakers() -> None:
    embeddings = [[1, 0], [0.99, 0.01], [0.8, 0.6], [0.75, 0.66], [0.2, 0.98]]
    durations = [2.0, 2.1, 0.4, 0.6, 0.5]
    labels = LocalAnalyzer._cluster_speaker_embeddings(embeddings, durations=durations)
    assert labels == [0, 0, 0, 0, 0]


def test_exact_two_speakers_stays_bounded_with_many_noisy_samples() -> None:
    embeddings = []
    durations = []
    for index in range(55):
        if index % 2:
            embeddings.append([0.03 + (index % 5) * 0.005, 0.99])
        else:
            embeddings.append([0.99, 0.03 + (index % 7) * 0.004])
        durations.append(0.5 if index % 4 == 0 else 1.8)
    labels = LocalAnalyzer._cluster_speaker_embeddings(
        embeddings, expected_count=2, durations=durations
    )
    assert len(set(labels)) == 2


def test_overlap_channels_reject_duplicate_bleed_through() -> None:
    channels = [
        [WordToken(text="Same words", start=0, end=1, confidence=0.8)],
        [WordToken(text="Same words", start=0, end=1, confidence=0.7)],
    ]
    try:
        LocalAnalyzer._deduplicate_overlap_channels(channels)
    except Exception as exc:
        assert getattr(exc, "code", None) == "overlap_not_found"
    else:
        raise AssertionError("duplicate separated channels must not be proposed")
