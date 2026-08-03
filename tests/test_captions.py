from accessible_caption_studio.captions import (
    parse_caption_text,
    to_srt,
    to_transcript_html,
    to_vtt,
)
from accessible_caption_studio.models import CaptionCue, SourceType


def test_srt_and_vtt_round_trip_unicode() -> None:
    cues = [
        CaptionCue(start=1.25, end=3.5, text="Café — hello!", speaker="Speaker 1"),
        CaptionCue(start=4, end=5.25, text="[door closes]", source=SourceType.SOUND),
    ]
    srt = to_srt(cues)
    vtt = to_vtt(cues)
    assert "01,250 --> 00:00:03,500" in srt
    assert "Speaker 1: Café — hello!" in srt
    assert vtt.startswith("WEBVTT")
    parsed = parse_caption_text(vtt)
    assert [cue.text for cue in parsed] == ["Café — hello!", "[door closes]"]
    assert parsed[0].speaker == "Speaker 1"


def test_grouped_speech_exports_as_one_two_voice_caption() -> None:
    cues = [
        CaptionCue(start=1, end=3, text="I disagree.", speaker="Speaker 1", overlap_group_id="g"),
        CaptionCue(
            start=1,
            end=3,
            text="Let me finish.",
            speaker="Speaker 2",
            overlap_group_id="g",
        ),
    ]
    srt = to_srt(cues)
    vtt = to_vtt(cues)
    assert srt.count("-->") == 1
    assert "Speaker 1: I disagree.\nSpeaker 2: Let me finish." in srt
    assert "<v Speaker 1>I disagree.</v>" in vtt
    parsed = parse_caption_text(vtt)
    assert [cue.speaker for cue in parsed] == ["Speaker 1", "Speaker 2"]
    assert parsed[0].overlap_group_id == parsed[1].overlap_group_id
    parsed_srt = parse_caption_text(srt)
    assert [cue.speaker for cue in parsed_srt] == ["Speaker 1", "Speaker 2"]
    assert parsed_srt[0].overlap_group_id == parsed_srt[1].overlap_group_id


def test_grouped_speech_transcript_preserves_both_speakers() -> None:
    cues = [
        CaptionCue(start=0, end=2, text="First", speaker="Speaker 1", overlap_group_id="g"),
        CaptionCue(start=0, end=2, text="Second", speaker="Speaker 2", overlap_group_id="g"),
    ]
    document = to_transcript_html("Overlap", cues)
    assert "<strong>Speaker 1:</strong> First<br><strong>Speaker 2:</strong> Second" in document


def test_parser_rejects_empty_input() -> None:
    try:
        parse_caption_text("WEBVTT\n\n")
    except ValueError as exc:
        assert "no valid" in str(exc)
    else:
        raise AssertionError("empty caption files must fail")


def test_transcript_escapes_user_content() -> None:
    document = to_transcript_html(
        "A <test>",
        [CaptionCue(start=0, end=2, text="<script>alert(1)</script>", speaker="A&B")],
    )
    assert "<script>alert" not in document
    assert "&lt;script&gt;" in document
    assert "A&amp;B" in document
