from __future__ import annotations

import html
import re
from pathlib import Path

from .models import CaptionCue, SourceType

_TIMESTAMP = re.compile(
    r"(?P<sh>\d{1,2}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{1,2}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)
_TAG = re.compile(r"<[^>]+>")


def _seconds(hours: str, minutes: str, seconds: str, milliseconds: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def parse_caption_text(content: str) -> list[CaptionCue]:
    lines = content.lstrip("\ufeff").replace("\r\n", "\n").splitlines()
    cues: list[CaptionCue] = []
    index = 0
    while index < len(lines):
        match = _TIMESTAMP.search(lines[index].strip())
        if not match:
            index += 1
            continue
        values = match.groupdict()
        start = _seconds(values["sh"], values["sm"], values["ss"], values["sms"])
        end = _seconds(values["eh"], values["em"], values["es"], values["ems"])
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1
        text = html.unescape(_TAG.sub("", " ".join(text_lines)))
        if not text.strip():
            raise ValueError(f"caption at {start:.3f}s has no text")
        cues.append(CaptionCue(start=start, end=end, text=text, source=SourceType.IMPORTED))
    if not cues:
        raise ValueError("no valid SRT or VTT caption cues were found")
    return cues


def parse_caption_file(path: Path) -> list[CaptionCue]:
    if path.suffix.lower() not in {".srt", ".vtt"}:
        raise ValueError("captions must be an SRT or VTT file")
    try:
        return parse_caption_text(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError("captions must use UTF-8 encoding") from exc


def _timestamp(value: float, separator: str) -> str:
    total_ms = max(0, round(value * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{milliseconds:03}"


def cue_display_text(cue: CaptionCue) -> str:
    if cue.speaker and cue.source != SourceType.SOUND:
        return f"{cue.speaker}: {cue.text}"
    return cue.text


def to_srt(cues: list[CaptionCue]) -> str:
    blocks = []
    for index, cue in enumerate(sorted(cues, key=lambda item: (item.start, item.end)), 1):
        blocks.append(
            f"{index}\n{_timestamp(cue.start, ',')} --> {_timestamp(cue.end, ',')}\n"
            f"{cue_display_text(cue)}"
        )
    return "\n\n".join(blocks) + "\n"


def to_vtt(cues: list[CaptionCue]) -> str:
    blocks = ["WEBVTT"]
    for cue in sorted(cues, key=lambda item: (item.start, item.end)):
        blocks.append(
            f"{_timestamp(cue.start, '.')} --> {_timestamp(cue.end, '.')}\n{cue_display_text(cue)}"
        )
    return "\n\n".join(blocks) + "\n"


def to_transcript_html(title: str, cues: list[CaptionCue]) -> str:
    rows: list[str] = []
    for cue in sorted(cues, key=lambda item: (item.start, item.end)):
        minutes, seconds = divmod(int(cue.start), 60)
        hours, minutes = divmod(minutes, 60)
        stamp = f"{hours:02}:{minutes:02}:{seconds:02}"
        speaker = f"<strong>{html.escape(cue.speaker)}:</strong> " if cue.speaker else ""
        rows.append(
            f'<li><time datetime="PT{cue.start:.3f}S">{stamp}</time> '
            f"{speaker}{html.escape(cue.text)}</li>"
        )
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title} — Accessible transcript</title>
  <style>
    body{{font:18px/1.6 system-ui;max-width:52rem;margin:auto;padding:2rem;color:#172033}}
    time{{font-variant-numeric:tabular-nums;color:#526077}}li{{margin:.7rem 0}}
  </style>
</head>
<body><main><h1>{safe_title}</h1>
<p>Accessible transcript with timestamps, speakers, and meaningful sounds.</p>
<ol>{"".join(rows)}</ol></main></body>
</html>
"""
