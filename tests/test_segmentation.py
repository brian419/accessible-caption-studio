from accessible_caption_studio.models import CaptionCue, SpeakerTurn, WordToken
from accessible_caption_studio.segmentation import assign_speakers, segment_words, wrap_caption


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
