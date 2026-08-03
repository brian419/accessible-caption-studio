from __future__ import annotations

import array
import math
import re
import sys
import wave
from difflib import SequenceMatcher
from pathlib import Path

from .models import WordToken


def _normalized(text: str) -> str:
    return re.sub(r"[^\w']+", "", text.casefold())


def _rms_windows(path: Path, window_seconds: float = 0.25) -> list[tuple[float, float]]:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        width = source.getsampwidth()
        channels = source.getnchannels()
        frame_count = source.getnframes()
        frames_per_window = max(1, round(rate * window_seconds))
        result: list[tuple[float, float]] = []
        position = 0
        while position < frame_count:
            frames = source.readframes(min(frames_per_window, frame_count - position))
            if width != 2 or not frames:
                result.append((position / rate, 0.0))
                position += frames_per_window
                continue
            values = array.array("h", frames)
            if sys.byteorder == "big":
                values.byteswap()
            if channels > 1:
                values = array.array("h", values[::channels])
            rms = math.sqrt(sum(value * value for value in values) / max(1, len(values)))
            result.append((position / rate, rms))
            position += frames_per_window
    return result


def detect_recovery_regions(
    audio_path: Path,
    words: list[WordToken],
    camera_cuts: list[float] | None = None,
) -> list[tuple[float, float]]:
    """Find bounded regions worth a context-free Whisper retry."""

    if not words:
        return []
    energy = _rms_windows(audio_path)
    nonzero = sorted(value for _, value in energy if value > 0)
    noise = nonzero[max(0, len(nonzero) // 4 - 1)] if nonzero else 0
    threshold = max(220.0, noise * 2.2)

    def energetic(start: float, end: float) -> bool:
        values = [value for time, value in energy if start <= time < end]
        return bool(
            values
            and max(values) >= threshold
            and sum(values) / len(values) >= threshold * 0.55
        )

    regions: list[tuple[float, float]] = []
    for word in words:
        if word.confidence is not None and word.confidence < 0.62:
            regions.append((max(0.0, word.start - 0.7), word.end + 0.7))
    for left, right in zip(words, words[1:], strict=False):
        gap = right.start - left.end
        if 0.28 <= gap <= 3.0 and energetic(left.end, right.start):
            regions.append((max(0.0, left.end - 0.65), right.start + 0.65))
    for cut in camera_cuts or []:
        nearby = [word for word in words if word.start - 0.5 <= cut <= word.end + 0.5]
        if nearby:
            regions.append((max(0.0, cut - 1.1), cut + 1.1))
    return merge_regions(regions)


def merge_regions(regions: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(regions):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 1.5 and end - merged[-1][0] <= 15:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, min(end, start + 15)])
    maximum_total = 50.0
    if sum(end - start for start, end in merged) > maximum_total:
        selected: list[list[float]] = []
        used = 0.0
        for region in sorted(merged, key=lambda item: item[1] - item[0]):
            duration = region[1] - region[0]
            if used + duration <= maximum_total:
                selected.append(region)
                used += duration
        merged = sorted(selected)
    return [(round(start, 3), round(end, 3)) for start, end in merged]


def _same_moment(left: WordToken, right: WordToken) -> bool:
    overlap = max(0.0, min(left.end, right.end) - max(left.start, right.start))
    shorter = max(0.04, min(left.end - left.start, right.end - right.start))
    midpoint_gap = abs((left.start + left.end - right.start - right.end) / 2)
    return overlap / shorter >= 0.5 or midpoint_gap <= 0.18


def merge_recovery_words(
    primary: list[WordToken], recovery: list[WordToken]
) -> tuple[list[WordToken], dict[str, int]]:
    """Merge by acoustic time, never by text appearing elsewhere in the program."""

    merged = [word.model_copy(deep=True) for word in primary]
    inserted = 0
    replaced = 0
    discarded = 0
    utterances: list[list[WordToken]] = []
    usable_recovery = [word for word in recovery if (word.confidence or 0) >= 0.35]
    for candidate in sorted(usable_recovery, key=lambda word: (word.start, word.end)):
        if not utterances or candidate.start - utterances[-1][-1].end > 1.1:
            utterances.append([])
        utterances[-1].append(candidate)

    for utterance in utterances:
        start, end = utterance[0].start, utterance[-1].end
        matches = [word for word in merged if word.start < end + 0.15 and word.end > start - 0.15]
        recovery_text = " ".join(_normalized(word.text) for word in utterance)
        primary_text = " ".join(_normalized(word.text) for word in matches)
        similarity = SequenceMatcher(None, recovery_text, primary_text).ratio()
        recovery_values = [word.confidence or 0 for word in utterance]
        primary_values = [word.confidence or 0 for word in matches]
        recovery_confidence = sum(recovery_values) / len(recovery_values)
        primary_confidence = (
            sum(primary_values) / len(primary_values) if primary_values else 0.0
        )

        should_replace = bool(
            matches
            and similarity < 0.62
            and recovery_confidence >= 0.65
            and (
                primary_confidence < 0.55
                or recovery_confidence >= primary_confidence + 0.18
            )
        )
        if should_replace:
            recovery_tokens = {_normalized(word.text) for word in utterance}
            trailing_rescue = [
                word.model_copy(deep=True)
                for word in matches
                if (word.confidence or 0) >= 0.8
                and _normalized(word.text) not in recovery_tokens
                and end - 0.2 <= word.end <= end + 1.0
            ]
            for word in matches:
                merged.remove(word)
            merged.extend(
                word.model_copy(update={"transcription_source": "recovery"})
                for word in utterance
            )
            for rescued in trailing_rescue:
                rescued.start = max(rescued.start, end + 0.02)
                rescued.end = max(rescued.start, rescued.end)
                merged.append(rescued)
            replaced += len(matches)
            continue
        if not matches and recovery_confidence >= 0.65:
            merged.extend(
                word.model_copy(update={"transcription_source": "recovery"})
                for word in utterance
            )
            inserted += len(utterance)
            continue
        if similarity >= 0.62:
            for candidate in utterance:
                same_text = next(
                    (
                        word
                        for word in matches
                        if _same_moment(word, candidate)
                        and _normalized(word.text) == _normalized(candidate.text)
                    ),
                    None,
                )
                if same_text and (candidate.confidence or 0) > (
                    same_text.confidence or 0
                ):
                    same_text.confidence = candidate.confidence
        discarded += len(utterance)
    merged.sort(key=lambda word: (word.start, word.end))
    return merged, {"inserted": inserted, "replaced": replaced, "discarded": discarded}
