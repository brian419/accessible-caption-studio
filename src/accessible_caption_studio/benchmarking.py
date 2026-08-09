from __future__ import annotations

import itertools
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from typing import Any

_WORD_RE = re.compile(r"[\w']+", re.UNICODE)


def _levenshtein_distance(reference: Sequence[Any], hypothesis: Sequence[Any]) -> int:
    if not reference:
        return len(hypothesis)
    if not hypothesis:
        return len(reference)
    previous = list(range(len(hypothesis) + 1))
    for reference_index, reference_item in enumerate(reference, start=1):
        current = [reference_index]
        for hypothesis_index, hypothesis_item in enumerate(hypothesis, start=1):
            substitution = previous[hypothesis_index - 1] + (
                reference_item != hypothesis_item
            )
            insertion = current[hypothesis_index - 1] + 1
            deletion = previous[hypothesis_index] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return previous[-1]


def normalized_words(text: str) -> list[str]:
    return [match.group(0).casefold() for match in _WORD_RE.finditer(text)]


def normalized_characters(text: str) -> list[str]:
    return [character for character in " ".join(normalized_words(text)) if not character.isspace()]


def word_error_counts(reference: str, hypothesis: str) -> tuple[int, int]:
    reference_words = normalized_words(reference)
    hypothesis_words = normalized_words(hypothesis)
    return _levenshtein_distance(reference_words, hypothesis_words), len(reference_words)


def character_error_counts(reference: str, hypothesis: str) -> tuple[int, int]:
    reference_characters = normalized_characters(reference)
    hypothesis_characters = normalized_characters(hypothesis)
    return (
        _levenshtein_distance(reference_characters, hypothesis_characters),
        len(reference_characters),
    )


def _rate(errors: int, reference_units: int) -> float:
    if reference_units:
        return errors / reference_units
    return 0.0 if errors == 0 else 1.0


def word_error_rate(reference: str, hypothesis: str) -> float:
    return _rate(*word_error_counts(reference, hypothesis))


def character_error_rate(reference: str, hypothesis: str) -> float:
    return _rate(*character_error_counts(reference, hypothesis))


def speaker_label_error_rate(
    reference: Sequence[str | None], hypothesis: Sequence[str | None]
) -> float | None:
    """Anonymous-speaker label error after choosing the best label permutation.

    The sequences must already be aligned benchmark units, such as words or fixed time windows.
    This intentionally measures label assignment quality and is not a full diarization DER.
    """
    if len(reference) != len(hypothesis):
        raise ValueError("speaker benchmark sequences must be aligned and have equal length")
    if not reference:
        return None

    reference_labels = sorted({item for item in reference if item is not None})
    hypothesis_labels = sorted({item for item in hypothesis if item is not None})
    if not hypothesis_labels:
        return sum(item is not None for item in reference) / len(reference)

    candidate_targets = reference_labels + [None] * max(0, len(hypothesis_labels) - len(reference_labels))
    best_errors = len(reference)
    for targets in itertools.permutations(candidate_targets, len(hypothesis_labels)):
        mapping = dict(zip(hypothesis_labels, targets, strict=True))
        errors = sum(
            expected != mapping.get(actual, actual if actual is None else None)
            for expected, actual in zip(reference, hypothesis, strict=True)
        )
        best_errors = min(best_errors, errors)
    return best_errors / len(reference)


def sound_event_scores(
    reference: Iterable[str], hypothesis: Iterable[str]
) -> dict[str, float | int]:
    reference_set = {item.casefold().strip() for item in reference if item.strip()}
    hypothesis_set = {item.casefold().strip() for item in hypothesis if item.strip()}
    true_positive = len(reference_set & hypothesis_set)
    false_positive = len(hypothesis_set - reference_set)
    false_negative = len(reference_set - hypothesis_set)
    precision = true_positive / (true_positive + false_positive) if hypothesis_set else 0.0
    recall = true_positive / (true_positive + false_negative) if reference_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_records(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, float] = defaultdict(float)
    category_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    speaker_rates: list[float] = []
    sound_totals = {"true_positive": 0, "false_positive": 0, "false_negative": 0}

    for record in records:
        reference_text = str(record.get("reference_text", ""))
        hypothesis_text = str(record.get("hypothesis_text", ""))
        word_errors, word_count = word_error_counts(reference_text, hypothesis_text)
        character_errors, character_count = character_error_counts(reference_text, hypothesis_text)
        totals["word_errors"] += word_errors
        totals["reference_words"] += word_count
        totals["character_errors"] += character_errors
        totals["reference_characters"] += character_count

        if "runtime_seconds" in record:
            totals["runtime_seconds"] += max(0.0, float(record["runtime_seconds"]))
            totals["runtime_samples"] += 1
        if "peak_memory_mb" in record:
            totals["peak_memory_mb"] += max(0.0, float(record["peak_memory_mb"]))
            totals["memory_samples"] += 1

        reference_speakers = record.get("reference_speakers")
        hypothesis_speakers = record.get("hypothesis_speakers")
        if reference_speakers is not None and hypothesis_speakers is not None:
            speaker_rate = speaker_label_error_rate(reference_speakers, hypothesis_speakers)
            if speaker_rate is not None:
                speaker_rates.append(speaker_rate)

        sound_scores = sound_event_scores(
            record.get("reference_sounds", []), record.get("hypothesis_sounds", [])
        )
        for key in sound_totals:
            sound_totals[key] += int(sound_scores[key])

        category = str(record.get("category", "uncategorized")).strip() or "uncategorized"
        category_records[category].append(record)

    precision_denominator = sound_totals["true_positive"] + sound_totals["false_positive"]
    recall_denominator = sound_totals["true_positive"] + sound_totals["false_negative"]
    sound_precision = (
        sound_totals["true_positive"] / precision_denominator if precision_denominator else 0.0
    )
    sound_recall = sound_totals["true_positive"] / recall_denominator if recall_denominator else 0.0
    sound_f1 = (
        2 * sound_precision * sound_recall / (sound_precision + sound_recall)
        if sound_precision + sound_recall
        else 0.0
    )

    result: dict[str, Any] = {
        "record_count": len(records),
        "word_error_rate": _rate(int(totals["word_errors"]), int(totals["reference_words"])),
        "character_error_rate": _rate(
            int(totals["character_errors"]), int(totals["reference_characters"])
        ),
        "speaker_label_error_rate": (
            sum(speaker_rates) / len(speaker_rates) if speaker_rates else None
        ),
        "sound_event_precision": sound_precision,
        "sound_event_recall": sound_recall,
        "sound_event_f1": sound_f1,
        "average_runtime_seconds": (
            totals["runtime_seconds"] / totals["runtime_samples"]
            if totals["runtime_samples"]
            else None
        ),
        "average_peak_memory_mb": (
            totals["peak_memory_mb"] / totals["memory_samples"]
            if totals["memory_samples"]
            else None
        ),
    }
    result["categories"] = {
        category: {
            key: value
            for key, value in evaluate_records(items).items()
            if key != "categories"
        }
        for category, items in category_records.items()
        if len(category_records) > 1
    }
    return result
