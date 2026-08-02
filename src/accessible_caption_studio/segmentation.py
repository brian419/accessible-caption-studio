from __future__ import annotations

import re

from .models import CaptionCue, SourceType, SpeakerTurn, WordToken

MAX_CHARS = 84
MAX_DURATION = 7.0
MIN_DURATION = 1.0
PAUSE_BOUNDARY = 0.65


def _confidence(words: list[WordToken]) -> float | None:
    values = [word.confidence for word in words if word.confidence is not None]
    return sum(values) / len(values) if values else None


def segment_words(words: list[WordToken]) -> list[CaptionCue]:
    if not words:
        return []
    cues: list[CaptionCue] = []
    group: list[WordToken] = []
    for index, word in enumerate(words):
        group.append(word)
        next_word = words[index + 1] if index + 1 < len(words) else None
        text = " ".join(item.text.strip() for item in group).strip()
        duration = word.end - group[0].start
        sentence_end = bool(re.search(r"[.!?][\"']?$", word.text.strip()))
        pause = next_word is None or next_word.start - word.end >= PAUSE_BOUNDARY
        too_long = len(text) >= MAX_CHARS or duration >= MAX_DURATION
        if next_word is None or too_long or (duration >= MIN_DURATION and (sentence_end or pause)):
            cues.append(
                CaptionCue(
                    start=group[0].start,
                    end=max(word.end, group[0].start + MIN_DURATION),
                    text=text,
                    source=SourceType.TRANSCRIPTION,
                    confidence=_confidence(group),
                )
            )
            group = []
    return cues


def assign_speakers(cues: list[CaptionCue], turns: list[SpeakerTurn]) -> list[CaptionCue]:
    for cue in cues:
        best_speaker = None
        best_overlap = 0.0
        for turn in turns:
            overlap = max(0.0, min(cue.end, turn.end) - max(cue.start, turn.start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = turn.speaker
        cue.speaker = best_speaker
    return cues


def wrap_caption(text: str, width: int = 42) -> str:
    words = text.split()
    if not words:
        return ""
    lines = [words[0]]
    for word in words[1:]:
        candidate = f"{lines[-1]} {word}"
        if len(candidate) <= width or len(lines) >= 2:
            lines[-1] = candidate
        else:
            lines.append(word)
    return "\n".join(lines)
