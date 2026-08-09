from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

from .models import CaptionCue, SourceType

_TIMESTAMP = re.compile(
    r"(?P<sh>\d{1,2}):(?P<sm>\d{2}):(?P<ss>\d{2})[,.](?P<sms>\d{3})\s*-->\s*"
    r"(?P<eh>\d{1,2}):(?P<em>\d{2}):(?P<es>\d{2})[,.](?P<ems>\d{3})"
)
_TAG = re.compile(r"<[^>]+>")
_VOICE = re.compile(r"^<v(?:\.\w+)*\s+([^>]+)>(.*?)(?:</v>)?$", re.IGNORECASE)
_ANONYMOUS_SPEAKER = re.compile(r"^(Speaker \d+):\s*(.+)$", re.IGNORECASE)


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
        voices = []
        for line in text_lines:
            voice = _VOICE.match(line)
            if voice:
                voices.append(
                    (
                        html.unescape(voice.group(1).strip()),
                        html.unescape(voice.group(2).strip()),
                    )
                )
        if voices:
            group_id = uuid4().hex if len(voices) > 1 else None
            cues.extend(
                CaptionCue(
                    start=start,
                    end=end,
                    text=text,
                    speaker=speaker,
                    source=SourceType.IMPORTED,
                    overlap_group_id=group_id,
                )
                for speaker, text in voices
            )
            continue
        speaker_lines = [
            match
            for line in text_lines
            if (match := _ANONYMOUS_SPEAKER.match(html.unescape(_TAG.sub("", line))))
        ]
        if speaker_lines and len(speaker_lines) == len(text_lines):
            group_id = uuid4().hex if len(speaker_lines) > 1 else None
            cues.extend(
                CaptionCue(
                    start=start,
                    end=end,
                    text=match.group(2).strip(),
                    speaker=match.group(1),
                    source=SourceType.IMPORTED,
                    overlap_group_id=group_id,
                )
                for match in speaker_lines
            )
            continue
        text = html.unescape(_TAG.sub("", " ".join(text_lines)))
        if not text.strip():
            raise ValueError(f"caption at {start:.3f}s has no text")
        cues.append(CaptionCue(start=start, end=end, text=text, source=SourceType.IMPORTED))
    if not cues:
        raise ValueError("no valid SRT or VTT caption cues were found")
    return cues


def _ttml_seconds(value: str) -> float:
    cleaned = value.strip()
    if cleaned.endswith("ms"):
        return float(cleaned[:-2]) / 1000
    if cleaned.endswith("s"):
        return float(cleaned[:-1])
    parts = cleaned.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"unsupported TTML time expression: {value}")


def parse_ttml_text(content: str) -> list[CaptionCue]:
    try:
        root = ET.fromstring(content.lstrip("\ufeff"))
    except ET.ParseError as exc:
        raise ValueError("TTML captions contain invalid XML") from exc
    cues: list[CaptionCue] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "p":
            continue
        begin = element.attrib.get("begin")
        end = element.attrib.get("end")
        duration = element.attrib.get("dur")
        if not begin or (not end and not duration):
            continue
        try:
            start = _ttml_seconds(begin)
            finish = _ttml_seconds(end) if end else start + _ttml_seconds(duration or "0s")
        except (TypeError, ValueError) as exc:
            raise ValueError("TTML captions use an unsupported time expression") from exc
        text = " ".join("".join(element.itertext()).split()).strip()
        if not text:
            continue
        speaker = element.attrib.get("data-speaker")
        anonymous = _ANONYMOUS_SPEAKER.match(text)
        if not speaker and anonymous:
            speaker = anonymous.group(1)
            text = anonymous.group(2).strip()
        cues.append(
            CaptionCue(
                start=max(0, start),
                end=max(start, finish),
                text=text,
                speaker=speaker,
                source=SourceType.IMPORTED,
            )
        )
    if not cues:
        raise ValueError("no valid TTML caption cues were found")
    return cues


def parse_caption_file(path: Path) -> list[CaptionCue]:
    suffix = path.suffix.lower()
    if suffix not in {".srt", ".vtt", ".ttml", ".dfxp"}:
        raise ValueError("captions must be an SRT, VTT, TTML, or DFXP file")
    try:
        content = path.read_text(encoding="utf-8")
        return parse_ttml_text(content) if suffix in {".ttml", ".dfxp"} else parse_caption_text(content)
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


def caption_groups(cues: list[CaptionCue]) -> list[list[CaptionCue]]:
    grouped: dict[str, list[CaptionCue]] = {}
    result: list[list[CaptionCue]] = []
    for cue in sorted(cues, key=lambda item: (item.start, item.end)):
        if cue.overlap_group_id:
            group = grouped.get(cue.overlap_group_id)
            if group is None:
                group = []
                grouped[cue.overlap_group_id] = group
                result.append(group)
            group.append(cue)
        else:
            result.append([cue])
    return result


def to_srt(cues: list[CaptionCue]) -> str:
    blocks = []
    for index, group in enumerate(caption_groups(cues), 1):
        cue = group[0]
        text = "\n".join(cue_display_text(item) for item in group)
        blocks.append(
            f"{index}\n{_timestamp(cue.start, ',')} --> {_timestamp(cue.end, ',')}\n"
            f"{text}"
        )
    return "\n\n".join(blocks) + "\n"


def to_vtt(cues: list[CaptionCue]) -> str:
    blocks = ["WEBVTT"]
    for group in caption_groups(cues):
        cue = group[0]
        text = "\n".join(
            f"<v {item.speaker}>{item.text}</v>" if item.speaker else item.text for item in group
        )
        blocks.append(
            f"{_timestamp(cue.start, '.')} --> {_timestamp(cue.end, '.')}\n{text}"
        )
    return "\n\n".join(blocks) + "\n"



def _ttml_timestamp(value: float) -> str:
    total_ms = max(0, round(value * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def to_ttml(cues: list[CaptionCue], language: str = "en") -> str:
    namespace = "http://www.w3.org/ns/ttml"
    xml_namespace = "http://www.w3.org/XML/1998/namespace"
    ET.register_namespace("", namespace)
    root = ET.Element(f"{{{namespace}}}tt")
    root.set(f"{{{xml_namespace}}}lang", "und" if language == "auto" else language)
    body = ET.SubElement(root, f"{{{namespace}}}body")
    division = ET.SubElement(body, f"{{{namespace}}}div")
    for group in caption_groups(cues):
        cue = group[0]
        element = ET.SubElement(
            division,
            f"{{{namespace}}}p",
            {"begin": _ttml_timestamp(cue.start), "end": _ttml_timestamp(cue.end)},
        )
        element.text = "\n".join(cue_display_text(item) for item in group)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    ) + "\n"


def to_transcript_html(title: str, cues: list[CaptionCue]) -> str:
    rows: list[str] = []
    for group in caption_groups(cues):
        cue = group[0]
        minutes, seconds = divmod(int(cue.start), 60)
        hours, minutes = divmod(minutes, 60)
        stamp = f"{hours:02}:{minutes:02}:{seconds:02}"
        utterances = []
        for item in group:
            speaker = f"<strong>{html.escape(item.speaker)}:</strong> " if item.speaker else ""
            utterances.append(f"{speaker}{html.escape(item.text)}")
        rows.append(
            f'<li><time datetime="PT{cue.start:.3f}S">{stamp}</time> '
            f"{'<br>'.join(utterances)}</li>"
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
