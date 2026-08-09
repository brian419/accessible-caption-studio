from __future__ import annotations

from .models import CaptionCue, CaptionStyle, Severity, ValidationFinding


def validate_cues(cues: list[CaptionCue], duration: float | None = None) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    ordered = sorted(cues, key=lambda cue: (cue.start, cue.end))
    overlap_groups: dict[str, list[CaptionCue]] = {}
    for cue in ordered:
        if cue.overlap_group_id:
            overlap_groups.setdefault(cue.overlap_group_id, []).append(cue)
    for grouped in overlap_groups.values():
        if len(grouped) < 2:
            findings.append(
                _finding(
                    "overlap_incomplete",
                    "A simultaneous caption needs two speaker lines.",
                    grouped[0],
                )
            )
        if len(grouped) > 2:
            findings.append(
                _finding(
                    "overlap_speaker_count",
                    "Simultaneous captions support at most two speakers.",
                    grouped[0],
                    True,
                )
            )
        if any(not cue.speaker for cue in grouped):
            findings.append(
                _finding(
                    "overlap_missing_speaker",
                    "Each simultaneous caption needs a speaker label.",
                    grouped[0],
                )
            )
        speakers = [cue.speaker for cue in grouped if cue.speaker]
        if len(speakers) > 1 and len(set(speakers)) != len(speakers):
            findings.append(
                _finding(
                    "overlap_duplicate_speaker",
                    "Simultaneous lines should use different speaker labels.",
                    grouped[0],
                )
            )
        if any(
            abs(cue.start - grouped[0].start) > 0.05 or abs(cue.end - grouped[0].end) > 0.05
            for cue in grouped[1:]
        ):
            findings.append(
                _finding(
                    "overlap_timing_mismatch",
                    "Simultaneous captions must share the same in and out times.",
                    grouped[0],
                    True,
                )
            )
        group_duration = grouped[0].end - grouped[0].start
        group_characters = sum(len(cue.text.replace("\n", "")) for cue in grouped)
        if group_duration > 0 and group_characters / group_duration > 20:
            findings.append(
                _finding(
                    "overlap_reading_speed",
                    "Combined simultaneous speech exceeds 20 characters per second.",
                    grouped[0],
                )
            )
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
        previous = ordered[index - 1] if index else None
        intentional_overlap = bool(
            previous
            and cue.overlap_group_id
            and cue.overlap_group_id == previous.overlap_group_id
        )
        if previous and cue.start < previous.end and not intentional_overlap:
            findings.append(
                _finding("overlap", "Caption overlaps the previous caption.", cue, True)
            )
    if duration and ordered:
        intervals = sorted({(cue.start, cue.end) for cue in ordered})
        speech_coverage = 0.0
        coverage_end = 0.0
        for start, end in intervals:
            if start >= coverage_end:
                speech_coverage += max(0, end - start)
            elif end > coverage_end:
                speech_coverage += end - coverage_end
            coverage_end = max(coverage_end, end)
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


def caption_style_readability_findings(style: CaptionStyle) -> list[ValidationFinding]:
    """Check authoring choices that can make rendered captions harder to read.

    Solid color contrast uses the WCAG contrast formula. Translucent captions are reported
    as authoring guidance rather than a conformance result because the underlying video
    changes from frame to frame and is not known here.
    """
    findings: list[ValidationFinding] = []
    contrast = contrast_ratio(style.text_color, style.background_color)

    if style.background_opacity >= 0.65 and contrast < 4.5:
        findings.append(
            ValidationFinding(
                code="style_low_contrast",
                message=(
                    f"Caption text and background colors have {contrast:.2f}:1 contrast when "
                    "the background is opaque. Choose colors with at least 4.5:1 contrast for "
                    "normal-size text."
                ),
                severity=Severity.WARNING,
            )
        )

    if (
        style.background_opacity < 0.55
        and style.outline_size_percent < 0.1
        and style.shadow_size_percent < 0.1
    ):
        findings.append(
            ValidationFinding(
                code="style_weak_video_separation",
                message=(
                    "The caption background is highly transparent and the text has little "
                    "outline or shadow. Moving video may make the caption difficult to read."
                ),
                severity=Severity.WARNING,
            )
        )

    if style.font_size_percent < 5:
        findings.append(
            ValidationFinding(
                code="style_small_text",
                message=(
                    "Caption text is very small relative to the video frame. Preview the "
                    "result at the intended viewing size or increase the caption size."
                ),
                severity=Severity.INFO,
            )
        )

    if style.max_width_percent > 94:
        findings.append(
            ValidationFinding(
                code="style_edge_crowding",
                message=(
                    "Captions can extend very close to the video edge. Reduce maximum caption "
                    "width to leave a safer visual margin."
                ),
                severity=Severity.INFO,
            )
        )

    return findings


def contrast_ratio(first_hex: str, second_hex: str) -> float:
    first = _relative_luminance(first_hex)
    second = _relative_luminance(second_hex)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _relative_luminance(value: str) -> float:
    raw = value.lstrip("#")
    channels = [int(raw[index : index + 2], 16) / 255 for index in (0, 2, 4)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _finding(code: str, message: str, cue: CaptionCue, error: bool = False) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        message=message,
        severity=Severity.ERROR if error else Severity.WARNING,
        cue_id=cue.id,
    )
