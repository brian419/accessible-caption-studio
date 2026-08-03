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


def segment_words(
    words: list[WordToken], minimum_duration: float = MIN_DURATION
) -> list[CaptionCue]:
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
        if (
            next_word is None
            or too_long
            or pause
            or (duration >= MIN_DURATION and sentence_end)
        ):
            cues.append(
                CaptionCue(
                    start=group[0].start,
                    end=max(word.end, group[0].start + minimum_duration),
                    text=text,
                    source=SourceType.TRANSCRIPTION,
                    confidence=_confidence(group),
                )
            )
            group = []
    return cues


def speaker_for_interval(
    start: float, end: float, turns: list[SpeakerTurn]
) -> tuple[str | None, float | None]:
    best_turn = None
    best_overlap = 0.0
    for turn in turns:
        overlap = max(0.0, min(end, turn.end) - max(start, turn.start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_turn = turn
    if best_turn is None:
        return None, None
    return best_turn.speaker, best_turn.confidence


def _speaker_turn_for_interval(
    start: float, end: float, turns: list[SpeakerTurn]
) -> SpeakerTurn | None:
    best = max(
        turns,
        key=lambda turn: max(0.0, min(end, turn.end) - max(start, turn.start)),
        default=None,
    )
    if best is None or min(end, best.end) - max(start, best.start) <= 0:
        return None
    return best


def segment_words_by_speaker(
    words: list[WordToken], turns: list[SpeakerTurn]
) -> list[CaptionCue]:
    """Segment transcript words at supported, rather than momentary, speaker changes."""

    if not turns:
        return segment_words(words)
    assignments: list[tuple[str | None, float | None]] = [
        speaker_for_interval(word.start, word.end, turns) for word in words
    ]
    index = 1
    while index < len(words):
        previous_speaker = assignments[index - 1][0]
        speaker = assignments[index][0]
        if speaker == previous_speaker:
            index += 1
            continue
        run_end = index + 1
        while run_end < len(words) and assignments[run_end][0] == speaker:
            run_end += 1
        previous = words[index - 1]
        pause = words[index].start - previous.end
        sentence_end = bool(re.search(r"[.!?][\"']?$", previous.text.strip()))
        duration = words[run_end - 1].end - words[index].start
        confidences = [
            value for _, value in assignments[index:run_end] if value is not None
        ]
        confidence = sum(confidences) / len(confidences) if confidences else 0.0
        persistent = run_end - index >= 2 or duration >= 0.8
        evidence = _speaker_turn_for_interval(words[index].start, words[index].end, turns)
        strong_visual_reply = bool(
            evidence
            and evidence.method in {"voice_face", "face_only"}
            and (evidence.visual_confidence or 0) >= 0.65
            and (pause >= 0.2 or sentence_end)
        )
        if not (
            pause >= 0.35
            or sentence_end
            or strong_visual_reply
            or (persistent and confidence >= 0.7)
        ):
            assignments[index:run_end] = [
                (previous_speaker, value) for _, value in assignments[index:run_end]
            ]
        index = run_end

    runs: list[tuple[str | None, list[WordToken], list[float]]] = []
    for word, (speaker, confidence) in zip(words, assignments, strict=True):
        if not runs or runs[-1][0] != speaker:
            runs.append((speaker, [], []))
        runs[-1][1].append(word)
        if confidence is not None:
            runs[-1][2].append(confidence)

    cues: list[CaptionCue] = []
    for speaker, run_words, speaker_confidences in runs:
        for cue in segment_words(run_words, minimum_duration=0):
            cue.speaker = speaker
            if speaker_confidences and cue.confidence is not None:
                speaker_confidence = sum(speaker_confidences) / len(speaker_confidences)
                cue.confidence = min(cue.confidence, speaker_confidence)
            cues.append(cue)
    for cue, following in zip(cues, cues[1:], strict=False):
        if cue.end - cue.start >= 0.8:
            continue
        available_end = max(cue.end, following.start - 0.05)
        cue.end = min(cue.start + 0.8, available_end)
    return cues


def assign_speakers(cues: list[CaptionCue], turns: list[SpeakerTurn]) -> list[CaptionCue]:
    for cue in cues:
        cue.speaker, _ = speaker_for_interval(cue.start, cue.end, turns)
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
