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
    assert [cue.text for cue in parse_caption_text(vtt)] == [
        "Speaker 1: Café — hello!",
        "[door closes]",
    ]


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
