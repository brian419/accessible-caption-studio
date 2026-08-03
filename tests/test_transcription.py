from accessible_caption_studio.models import WordToken
from accessible_caption_studio.transcription import merge_recovery_words


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
