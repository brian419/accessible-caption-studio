from accessible_caption_studio.models import CaptionCue, SpeakerTurn, WordToken
from accessible_caption_studio.segmentation import (
    assign_speakers,
    segment_words,
    segment_words_by_speaker,
    wrap_caption,
)


def word(text: str, start: float, end: float, confidence: float = 0.9) -> WordToken:
    return WordToken(text=text, start=start, end=end, confidence=confidence)


def test_segments_on_sentence_and_pause() -> None:
    words = [
        word("Hello", 0, 0.4),
        word("there.", 0.45, 1.0),
        word("Welcome", 2, 2.5),
        word("back", 2.55, 3),
    ]
    cues = segment_words(words)
    assert [cue.text for cue in cues] == ["Hello there.", "Welcome back"]
    assert cues[0].confidence == 0.9
    assert all(cue.end > cue.start for cue in cues)


def test_assigns_speaker_with_greatest_overlap() -> None:
    cues = [CaptionCue(start=1, end=4, text="Hello")]
    turns = [
        SpeakerTurn(speaker="Speaker 1", start=0, end=1.5),
        SpeakerTurn(speaker="Speaker 2", start=1.5, end=4),
    ]
    assert assign_speakers(cues, turns)[0].speaker == "Speaker 2"


def test_wraps_to_two_lines() -> None:
    wrapped = wrap_caption("This caption should wrap onto another readable line", width=30)
    assert wrapped.count("\n") == 1


def test_speaker_change_splits_caption_without_losing_words() -> None:
    words = [
        word("How", 0, 0.3),
        word("are", 0.3, 0.6),
        word("you?", 0.6, 1.0),
        word("Fine.", 1.05, 1.5),
    ]
    turns = [
        SpeakerTurn(speaker="Speaker 1", start=0, end=1.02, confidence=0.9),
        SpeakerTurn(speaker="Speaker 2", start=1.02, end=1.6, confidence=0.85),
    ]
    cues = segment_words_by_speaker(words, turns)
    assert [(cue.speaker, cue.text) for cue in cues] == [
        ("Speaker 1", "How are you?"),
        ("Speaker 2", "Fine."),
    ]
    assert " ".join(cue.text for cue in cues) == "How are you? Fine."
    assert cues[0].end <= cues[1].start


def test_weak_final_word_change_does_not_split_a_sentence() -> None:
    words = [
        word("I've", 8.94, 9.2),
        word("been", 9.2, 9.5),
        word("trying", 9.5, 9.9),
        word("to", 9.9, 10.0),
        word("reach", 10.0, 10.35),
        word("out", 10.35, 10.6),
        word("to", 10.6, 10.75),
        word("you", 10.75, 10.95),
        word("all", 10.95, 11.14),
        word("day.", 11.14, 11.54),
    ]
    turns = [
        SpeakerTurn(speaker="Speaker 1", start=8.94, end=11.14, confidence=0.9),
        SpeakerTurn(speaker="Speaker 2", start=11.14, end=11.54, confidence=0.45),
    ]
    cues = segment_words_by_speaker(words, turns)
    assert [(cue.speaker, cue.text) for cue in cues] == [
        ("Speaker 1", "I've been trying to reach out to you all day.")
    ]


def test_short_reply_is_not_carried_across_a_long_pause() -> None:
    words = [
        word("What?", 22.9, 23.06),
        word("Oh,", 30.06, 30.28),
        word("shoot.", 30.28, 30.78),
    ]
    cues = segment_words(words)
    assert [cue.text for cue in cues] == ["What?", "Oh, shoot."]
    assert cues[0].end <= cues[1].start
