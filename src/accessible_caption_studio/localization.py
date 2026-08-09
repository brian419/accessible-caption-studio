from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import Path

from .errors import SetupError, StudioError
from .models import CaptionCue, CaptionTrack, Project, Severity, ValidationFinding, utc_now
from .validation import validate_cues

TRANSLATION_MODEL_ID = "facebook/m2m100_418M"
TRANSLATION_MODEL_LABEL = "M2M100 418M"
SUPPORTED_TRANSLATION_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "ru": "Russian",
    "uk": "Ukrainian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "hi": "Hindi",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "id": "Indonesian",
    "th": "Thai",
}

ProgressCallback = Callable[[str, int, str], None]


def normalize_target_languages(values: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in values:
        code = str(raw).strip().lower().split("-", 1)[0]
        if not code:
            continue
        if code not in SUPPORTED_TRANSLATION_LANGUAGES:
            raise ValueError(f"Translation is not available for language code {code!r}")
        if code not in cleaned:
            cleaned.append(code)
    return cleaned


def translate_texts_local(
    texts: list[str],
    source_language: str,
    target_language: str,
    model_dir: Path,
    progress: ProgressCallback | None = None,
) -> list[str]:
    if source_language not in SUPPORTED_TRANSLATION_LANGUAGES:
        raise StudioError(
            "translation_source_unsupported",
            "The detected spoken language is not available in the local translation model.",
        )
    if target_language not in SUPPORTED_TRANSLATION_LANGUAGES:
        raise StudioError(
            "translation_target_unsupported",
            "The selected caption language is not available in the local translation model.",
        )
    if source_language == target_language:
        return list(texts)
    if not texts:
        return []

    model_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=model_dir) as temporary_dir:
        temporary = Path(temporary_dir)
        input_path = temporary / "translation-input.json"
        output_path = temporary / "translation-output.json"
        input_path.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
        command = [
            sys.executable,
            "-m",
            "accessible_caption_studio.translation_worker",
            source_language,
            target_language,
            str(input_path),
            str(output_path),
            str(model_dir),
        ]
        runner = getattr(progress, "run_process", None)
        process = (
            runner(command)
            if runner
            else subprocess.run(command, capture_output=True, text=True, check=False)
        )
        if process.returncode:
            detail = (process.stderr or process.stdout or "").strip()
            if "No module named" in detail and (
                "sentencepiece" in detail or "transformers" in detail
            ):
                raise SetupError(
                    "translation_not_installed",
                    "Local translation support is not installed. Run setup from the launcher.",
                )
            raise StudioError(
                "translation_failed",
                f"Local caption translation failed: {detail[-900:]}",
            )
        try:
            translated = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StudioError(
                "translation_failed", "The local translation model returned unreadable output."
            ) from exc
        if not isinstance(translated, list) or len(translated) != len(texts):
            raise StudioError(
                "translation_failed",
                "The local translation model returned an incomplete caption set.",
            )
        return [str(item).strip() for item in translated]


def translation_findings(
    source_cues: list[CaptionCue],
    translated_cues: list[CaptionCue],
    source_language: str,
    target_language: str,
    duration: float | None,
) -> list[ValidationFinding]:
    findings = validate_cues(translated_cues, duration)
    for source, translated in zip(source_cues, translated_cues, strict=False):
        source_text = " ".join(source.text.split()).strip()
        target_text = " ".join(translated.text.split()).strip()
        if not source_text:
            continue
        if not target_text:
            findings.append(
                ValidationFinding(
                    code="translation_empty",
                    message="Translation is empty. Review this caption before export.",
                    severity=Severity.ERROR,
                    cue_id=translated.id,
                )
            )
            continue

        if source_language != target_language and _normalized_text(source_text) == _normalized_text(target_text):
            findings.append(
                ValidationFinding(
                    code="translation_untranslated",
                    message="This caption is unchanged from the source language. Verify that it should remain untranslated.",
                    severity=Severity.INFO,
                    cue_id=translated.id,
                )
            )

        source_numbers = Counter(_numbers(source_text))
        target_numbers = Counter(_numbers(target_text))
        if source_numbers != target_numbers:
            findings.append(
                ValidationFinding(
                    code="translation_number_changed",
                    message="A number changed or disappeared during translation. Compare this caption with the original.",
                    severity=Severity.WARNING,
                    cue_id=translated.id,
                )
            )

        protected = _proper_names_and_acronyms(source_text)
        missing = [item for item in protected if item.casefold() not in target_text.casefold()]
        if missing:
            findings.append(
                ValidationFinding(
                    code="translation_name_changed",
                    message=(
                        "A proper name or acronym may have changed during translation: "
                        + ", ".join(missing[:4])
                        + "."
                    ),
                    severity=Severity.WARNING,
                    cue_id=translated.id,
                )
            )

        source_length = len(re.sub(r"\s+", "", source_text))
        target_length = len(re.sub(r"\s+", "", target_text))
        if source_length >= 12:
            ratio = target_length / max(1, source_length)
            if ratio < 0.4 or ratio > 2.5:
                findings.append(
                    ValidationFinding(
                        code="translation_length_shift",
                        message="The translated caption is unusually different in length from the source. Review wording and timing.",
                        severity=Severity.INFO,
                        cue_id=translated.id,
                    )
                )
    return findings


def create_translation_track(
    project: Project,
    target_language: str,
    model_dir: Path,
    progress: ProgressCallback | None = None,
    *,
    replace_existing: bool = False,
) -> CaptionTrack:
    target_language = normalize_target_languages([target_language])[0]
    source = project.original_caption_track()
    source_language = source.language.lower().split("-", 1)[0]
    if source_language in {"auto", "und"}:
        raise StudioError(
            "translation_source_unknown",
            "Choose a spoken language or run automatic transcription so the source language can be detected before translating.",
        )
    if source_language == target_language:
        raise StudioError(
            "translation_matches_source",
            "The original caption track already uses that language.",
        )
    if not source.cues:
        raise StudioError(
            "captions_required",
            "Create or import the original captions before adding a translation.",
        )

    existing = project.translation_caption_track(target_language)
    if existing is not None and not replace_existing:
        raise StudioError(
            "translation_exists",
            "A translated caption track already exists for that language.",
        )

    if progress:
        progress(
            "Translating captions",
            30,
            f"Translating {len(source.cues)} caption cues locally with {TRANSLATION_MODEL_LABEL}",
        )
    translated_texts = translate_texts_local(
        [cue.text for cue in source.cues],
        source_language,
        target_language,
        model_dir,
        progress,
    )
    translated_cues: list[CaptionCue] = []
    for source_cue, translated_text in zip(source.cues, translated_texts, strict=True):
        translated_cues.append(
            source_cue.model_copy(
                deep=True,
                update={"text": translated_text or source_cue.text},
            )
        )
    duration = project.media.duration if project.media else None
    findings = translation_findings(
        source.cues,
        translated_cues,
        source_language,
        target_language,
        duration,
    )

    now = utc_now()
    if existing is not None:
        existing.source_track_id = source.id
        existing.source_language = source_language
        existing.cues = translated_cues
        existing.findings = findings
        existing.exports = []
        existing.review_state = "unreviewed"
        existing.translation_model = TRANSLATION_MODEL_ID
        existing.updated_at = now
        track = existing
    else:
        track = CaptionTrack(
            language=target_language,
            kind="translation",
            source_track_id=source.id,
            source_language=source_language,
            review_state="unreviewed",
            cues=translated_cues,
            findings=findings,
            translation_model=TRANSLATION_MODEL_ID,
            created_at=now,
            updated_at=now,
        )
        project.caption_tracks.append(track)
    return track


def _normalized_text(value: str) -> str:
    return re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).strip().casefold()


def _numbers(value: str) -> list[str]:
    return re.findall(r"(?<!\w)\d+(?:[.,]\d+)?(?!\w)", value)


def _proper_names_and_acronyms(value: str) -> list[str]:
    words = re.findall(r"\b[^\W\d_][\w'’-]*\b", value, flags=re.UNICODE)
    protected: list[str] = []
    for index, word in enumerate(words):
        acronym = len(word) >= 2 and word.isupper()
        interior_name = index > 0 and len(word) >= 2 and word[:1].isupper() and word[1:].islower()
        if (acronym or interior_name) and word not in protected:
            protected.append(word)
    return protected
