from accessible_caption_studio.models import CaptionCue
from accessible_caption_studio.validation import validate_cues


def test_reports_timing_and_readability_problems() -> None:
    cues = [
        CaptionCue(start=0, end=0.5, text="A caption that is far too fast to read comfortably"),
        CaptionCue(start=0.4, end=9, text="Second caption"),
    ]
    codes = {finding.code for finding in validate_cues(cues, duration=8)}
    assert {"reading_speed", "too_short", "overlap", "too_long", "outside_media"} <= codes


def test_reports_empty_and_low_coverage_projects() -> None:
    assert validate_cues([], 10)[0].code == "no_captions"
    findings = validate_cues([CaptionCue(start=0, end=1, text="Hello")], 30)
    assert any(item.code == "low_coverage" for item in findings)


def test_clean_caption_has_no_findings() -> None:
    cues = [CaptionCue(start=0, end=2, text="A readable caption.")]
    assert validate_cues(cues, 2) == []
