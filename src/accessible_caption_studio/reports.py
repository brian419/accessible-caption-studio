from __future__ import annotations

import html
from collections import Counter

from .models import Project, Severity, SourceType
from .validation import caption_style_readability_findings, validate_cues


def _coverage(project: Project) -> float:
    if not project.media or project.media.duration <= 0 or not project.cues:
        return 0.0
    intervals = sorted((cue.start, cue.end) for cue in project.cues if cue.end > cue.start)
    covered = 0.0
    cursor = 0.0
    for start, end in intervals:
        if start >= cursor:
            covered += end - start
        elif end > cursor:
            covered += end - cursor
        cursor = max(cursor, end)
    return min(1.0, covered / project.media.duration)


def _reading_speeds(project: Project) -> list[float]:
    values: list[float] = []
    for cue in project.cues:
        duration = cue.end - cue.start
        if duration > 0:
            values.append(len(cue.text.replace("\n", "")) / duration)
    return values


def accessibility_report_html(project: Project) -> str:
    duration = project.media.duration if project.media else None
    findings = list(project.findings)
    known = {(item.code, item.cue_id, item.message) for item in findings}
    for finding in validate_cues(project.cues, duration):
        key = (finding.code, finding.cue_id, finding.message)
        if key not in known:
            findings.append(finding)
            known.add(key)
    findings.extend(caption_style_readability_findings(project.caption_style))
    severities = Counter(finding.severity.value for finding in findings)
    speeds = _reading_speeds(project)
    average_speed = sum(speeds) / len(speeds) if speeds else 0.0
    maximum_speed = max(speeds, default=0.0)
    speakers = len({cue.speaker for cue in project.cues if cue.speaker})
    sound_cues = sum(1 for cue in project.cues if cue.source == SourceType.SOUND)
    low_confidence = sum(
        1
        for cue in project.cues
        if cue.source != SourceType.SOUND
        and cue.confidence is not None
        and cue.confidence < 0.75
    )
    cue_lookup = {cue.id: cue for cue in project.cues}

    rows = []
    for finding in findings:
        cue = cue_lookup.get(finding.cue_id or "")
        location = f"{cue.start:.3f}s" if cue else "Project"
        rows.append(
            "<tr>"
            f"<td>{html.escape(finding.severity.value.title())}</td>"
            f"<td>{html.escape(finding.code)}</td>"
            f"<td>{html.escape(location)}</td>"
            f"<td>{html.escape(finding.message)}</td>"
            "</tr>"
        )
    finding_rows = "".join(rows) or (
        '<tr><td colspan="4">No automatic authoring findings are currently open.</td></tr>'
    )
    active_track = project.active_caption_track()
    language = active_track.language
    spoken_language = project.detected_language or project.spoken_language
    track_kind = active_track.kind.title()
    review_state = active_track.review_state.replace("_", " ").title()
    sdh = project.sdh_mode.title()
    safe_title = html.escape(project.name)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} - Accessibility authoring report</title>
  <style>
    body{{font:16px/1.55 system-ui,sans-serif;max-width:72rem;margin:auto;padding:2rem;color:#172033}}
    h1,h2{{line-height:1.2}} .summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.75rem}}
    .stat{{padding:.9rem;border:1px solid #d7deea;border-radius:.6rem}} .stat strong,.stat span{{display:block}}
    .stat strong{{font-size:1.35rem}} .stat span{{color:#526077}} table{{width:100%;border-collapse:collapse;margin-top:1rem}}
    th,td{{padding:.65rem;text-align:left;vertical-align:top;border-bottom:1px solid #d7deea}} th{{background:#f5f7fb}}
    .note{{padding:1rem;border-left:4px solid #2854d6;background:#eef4ff}} code{{overflow-wrap:anywhere}}
  </style>
</head>
<body><main>
  <p>Accessible Caption Studio</p>
  <h1>{safe_title} - Accessibility authoring report</h1>
  <p class="note">This is an authoring-quality report generated from the saved project. It is not a legal certification of WCAG, ADA, Section 508, or platform compliance.</p>
  <h2>Project summary</h2>
  <div class="summary">
    <div class="stat"><strong>{len(project.cues)}</strong><span>Caption cues</span></div>
    <div class="stat"><strong>{speakers}</strong><span>Speakers</span></div>
    <div class="stat"><strong>{sound_cues}</strong><span>Sound cues</span></div>
    <div class="stat"><strong>{low_confidence}</strong><span>Low-confidence cues</span></div>
    <div class="stat"><strong>{_coverage(project) * 100:.1f}%</strong><span>Timeline coverage</span></div>
    <div class="stat"><strong>{average_speed:.1f}</strong><span>Average characters/sec</span></div>
    <div class="stat"><strong>{maximum_speed:.1f}</strong><span>Maximum characters/sec</span></div>
    <div class="stat"><strong>{len(findings)}</strong><span>Open findings</span></div>
  </div>
  <p>Caption track: <strong>{html.escape(language)}</strong> ({html.escape(track_kind)}). Review state: <strong>{html.escape(review_state)}</strong>. Spoken language: <strong>{html.escape(spoken_language)}</strong>. Sound-caption mode: <strong>{html.escape(sdh)}</strong>.</p>
  <p>Findings by severity: {severities.get(Severity.ERROR.value, 0)} errors, {severities.get(Severity.WARNING.value, 0)} warnings, {severities.get(Severity.INFO.value, 0)} informational findings.</p>
  <h2>Outstanding authoring findings</h2>
  <table><thead><tr><th>Severity</th><th>Code</th><th>Location</th><th>Finding</th></tr></thead><tbody>{finding_rows}</tbody></table>
</main></body></html>"""
