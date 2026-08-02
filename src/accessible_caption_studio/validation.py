from __future__ import annotations

from .models import CaptionCue, Severity, ValidationFinding


def validate_cues(cues: list[CaptionCue], duration: float | None = None) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    ordered = sorted(cues, key=lambda cue: (cue.start, cue.end))
    for index, cue in enumerate(ordered):
        cue_duration = cue.end - cue.start
        lines = cue.text.splitlines() or [cue.text]
        if cue.end <= cue.start:
            findings.append(
                _finding("invalid_interval", "End time must follow start time.", cue, True)
            )
        if cue_duration > 0 and len(cue.text.replace("\n", "")) / cue_duration > 20:
            findings.append(
                _finding("reading_speed", "Reading speed exceeds 20 characters per second.", cue)
            )
        if any(len(line) > 42 for line in lines):
            findings.append(_finding("long_line", "A caption line exceeds 42 characters.", cue))
        if len(lines) > 2:
            findings.append(_finding("line_count", "Caption uses more than two lines.", cue))
        if 0 < cue_duration < 1:
            findings.append(
                _finding("too_short", "Caption is displayed for less than one second.", cue)
            )
        if cue_duration > 7:
            findings.append(
                _finding("too_long", "Caption is displayed for more than seven seconds.", cue)
            )
        if duration is not None and cue.end > duration + 0.05:
            findings.append(
                _finding("outside_media", "Caption extends beyond the media duration.", cue, True)
            )
        if index and cue.start < ordered[index - 1].end:
            findings.append(
                _finding("overlap", "Caption overlaps the previous caption.", cue, True)
            )
    if duration and ordered:
        speech_coverage = sum(max(0, cue.end - cue.start) for cue in ordered)
        if speech_coverage / duration < 0.1:
            findings.append(
                ValidationFinding(
                    code="low_coverage",
                    message=(
                        "Captions cover less than 10% of the media. "
                        "Check whether speech was missed."
                    ),
                    severity=Severity.INFO,
                )
            )
    if not ordered:
        findings.append(
            ValidationFinding(
                code="no_captions",
                message="This project does not contain captions.",
                severity=Severity.WARNING,
            )
        )
    return findings


def _finding(code: str, message: str, cue: CaptionCue, error: bool = False) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        message=message,
        severity=Severity.ERROR if error else Severity.WARNING,
        cue_id=cue.id,
    )
