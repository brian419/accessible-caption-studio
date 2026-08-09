import pytest

from accessible_caption_studio.benchmarking import (
    character_error_rate,
    evaluate_records,
    sound_event_scores,
    speaker_label_error_rate,
    word_error_rate,
)


def test_word_and_character_error_rates_normalize_case_and_punctuation() -> None:
    assert word_error_rate("Hello, WORLD!", "hello world") == 0
    assert character_error_rate("Caption", "caption") == 0
    assert word_error_rate("one two three", "one four three") == pytest.approx(1 / 3)


def test_speaker_error_ignores_anonymous_label_names() -> None:
    reference = ["Speaker 1", "Speaker 1", "Speaker 2", "Speaker 2"]
    hypothesis = ["Voice B", "Voice B", "Voice A", "Voice A"]
    assert speaker_label_error_rate(reference, hypothesis) == 0


def test_sound_event_scores_report_precision_recall_and_f1() -> None:
    scores = sound_event_scores(["applause", "music"], ["applause", "door closes"])
    assert scores["precision"] == pytest.approx(0.5)
    assert scores["recall"] == pytest.approx(0.5)
    assert scores["f1"] == pytest.approx(0.5)


def test_evaluate_records_reports_categories_and_resource_metrics() -> None:
    report = evaluate_records(
        [
            {
                "id": "clean-1",
                "category": "clean_speech",
                "reference_text": "hello there",
                "hypothesis_text": "hello there",
                "reference_speakers": ["Speaker 1", "Speaker 1"],
                "hypothesis_speakers": ["A", "A"],
                "reference_sounds": [],
                "hypothesis_sounds": [],
                "runtime_seconds": 2,
                "peak_memory_mb": 400,
            },
            {
                "id": "noise-1",
                "category": "background_noise",
                "reference_text": "hello there",
                "hypothesis_text": "hello",
                "reference_speakers": ["Speaker 1", "Speaker 2"],
                "hypothesis_speakers": ["A", "A"],
                "reference_sounds": ["music"],
                "hypothesis_sounds": ["music"],
                "runtime_seconds": 4,
                "peak_memory_mb": 600,
            },
        ]
    )

    assert report["record_count"] == 2
    assert report["word_error_rate"] == pytest.approx(0.25)
    assert report["average_runtime_seconds"] == pytest.approx(3)
    assert report["average_peak_memory_mb"] == pytest.approx(500)
    assert set(report["categories"]) == {"clean_speech", "background_noise"}
