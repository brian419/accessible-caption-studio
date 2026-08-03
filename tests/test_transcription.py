import wave
from pathlib import Path

from accessible_caption_studio.models import WordToken
from accessible_caption_studio.transcription import (
    detect_recovery_regions,
    merge_recovery_words,
)


def word(text: str, start: float, end: float, confidence: float) -> WordToken:
    return WordToken(text=text, start=start, end=end, confidence=confidence)


def test_time_separated_repeated_dialogue_is_preserved() -> None:
    primary = [word("Whatever.", 10, 10.8, 0.9)]
    recovery = [word("Whatever.", 12, 12.8, 0.9)]
    merged, summary = merge_recovery_words(primary, recovery)
    assert [(item.text, item.start) for item in merged] == [
        ("Whatever.", 10.0),
        ("Whatever.", 12.0),
    ]
    assert summary["inserted"] == 1


def test_overlapping_decoder_duplicate_is_kept_once() -> None:
    primary = [word("Whatever.", 10, 10.8, 0.8)]
    recovery = [word("whatever", 10.05, 10.82, 0.9)]
    merged, summary = merge_recovery_words(primary, recovery)
    assert len(merged) == 1
    assert merged[0].confidence == 0.9
    assert summary["discarded"] == 1


def test_higher_confidence_recovery_replaces_wrong_word_at_same_time() -> None:
    primary = [word("Cheese", 17.6, 18.1, 0.4)]
    recovery = [word("Geez.", 17.62, 18.12, 0.85)]
    merged, summary = merge_recovery_words(primary, recovery)
    assert [item.text for item in merged] == ["Geez."]
    assert merged[0].transcription_source == "recovery"
    assert summary["replaced"] == 1


def test_speech_coverage_recovers_a_long_gap_whisper_missed(tmp_path: Path) -> None:
    audio = tmp_path / "audio.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000 * 8)
    words = [
        word("Before", 0.5, 1.0, 0.9),
        word("After", 6.5, 7.0, 0.9),
    ]
    regions = detect_recovery_regions(
        audio,
        words,
        speech_regions=[(0.4, 7.1)],
    )
    assert any(start < 2 and end > 6 for start, end in regions)


def test_time_aligned_recovery_inserts_each_missing_word() -> None:
    primary = [
        word("I", 1.0, 1.2, 0.9),
        word("today.", 2.4, 2.8, 0.9),
    ]
    recovery = [
        word("called", 1.35, 1.7, 0.78),
        word("you", 1.75, 2.0, 0.82),
        word("twice", 2.05, 2.35, 0.8),
    ]
    merged, summary = merge_recovery_words(primary, recovery)
    assert [item.text for item in merged] == ["I", "called", "you", "twice", "today."]
    assert summary["inserted"] == 3
