from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one anchor in {path}, found {count}: {old[:100]!r}")
    write(path, content.replace(old, new, 1))


def append_once(path: str, marker: str, content_to_append: str) -> None:
    content = read(path)
    if marker in content:
        return
    write(path, content.rstrip() + "\n\n" + content_to_append.strip() + "\n")


# Python dependencies: M2M100 uses SentencePiece for its tokenizer.
replace_once(
    "pyproject.toml",
    '  "transformers>=4.48,<5",\n',
    '  "transformers>=4.48,<5",\n  "sentencepiece>=0.2,<1",\n',
)

# Project model: caption tracks become the source of truth while legacy cue/findings/export
# fields remain an active-track compatibility view for the existing editor.
replace_once(
    "src/accessible_caption_studio/models.py",
    '''class AnalysisJob(BaseModel):\n''',
    '''class CaptionTrack(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    language: str = Field(default="en", pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$")
    kind: Literal["original", "translation"] = "original"
    source_track_id: str | None = None
    source_language: str | None = Field(
        default=None, pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$"
    )
    review_state: Literal["unreviewed", "in_review", "reviewed", "needs_update"] = (
        "unreviewed"
    )
    cues: list[CaptionCue] = Field(default_factory=list)
    findings: list[ValidationFinding] = Field(default_factory=list)
    exports: list[ExportArtifact] = Field(default_factory=list)
    translation_model: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AnalysisJob(BaseModel):
''',
)
replace_once(
    "src/accessible_caption_studio/models.py",
    '''    transcription_language: str = Field(\n        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"\n    )\n    sdh_mode: Literal["off", "conservative", "full"] = "full"\n''',
    '''    transcription_language: str = Field(
        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"
    )
    spoken_language: str = Field(
        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"
    )
    detected_language: str | None = Field(
        default=None, pattern=r"^[a-z]{2,3}(?:-[A-Z]{2})?$"
    )
    requested_caption_languages: list[str] = Field(default_factory=list)
    caption_tracks: list[CaptionTrack] = Field(default_factory=list)
    active_caption_track_id: str | None = None
    sdh_mode: Literal["off", "conservative", "full"] = "full"
''',
)
replace_once(
    "src/accessible_caption_studio/models.py",
    '''    @field_validator("speaker_names")\n    @classmethod\n    def valid_speaker_names''',
    '''    @field_validator("requested_caption_languages")
    @classmethod
    def valid_requested_caption_languages(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            code = str(item).strip()
            if code in {"auto", "und"}:
                continue
            if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", code):
                raise ValueError("caption language is invalid")
            if code not in cleaned:
                cleaned.append(code)
        return cleaned

    @model_validator(mode="after")
    def synchronize_caption_track_state(self) -> Project:
        # transcription_language is retained as a compatibility alias for older clients.
        if self.spoken_language == "en" and self.transcription_language != "en":
            self.spoken_language = self.transcription_language
        self.transcription_language = self.spoken_language

        if not self.caption_tracks:
            original_language = self.detected_language or (
                self.spoken_language if self.spoken_language != "auto" else "und"
            )
            self.caption_tracks = [
                CaptionTrack(
                    language=original_language,
                    kind="original",
                    cues=[cue.model_copy(deep=True) for cue in self.cues],
                    findings=[finding.model_copy(deep=True) for finding in self.findings],
                    exports=[artifact.model_copy(deep=True) for artifact in self.exports],
                )
            ]

        ids = {track.id for track in self.caption_tracks}
        if self.active_caption_track_id not in ids:
            original = next(
                (track for track in self.caption_tracks if track.kind == "original"),
                self.caption_tracks[0],
            )
            self.active_caption_track_id = original.id
        self.refresh_caption_track_view()
        return self

    def caption_track(self, track_id: str | None = None) -> CaptionTrack | None:
        wanted = track_id or self.active_caption_track_id
        return next((track for track in self.caption_tracks if track.id == wanted), None)

    def active_caption_track(self) -> CaptionTrack:
        track = self.caption_track()
        if track is None:
            raise ValueError("Project has no active caption track")
        return track

    def original_caption_track(self) -> CaptionTrack:
        track = next(
            (item for item in self.caption_tracks if item.kind == "original"),
            None,
        )
        if track is None:
            raise ValueError("Project has no original caption track")
        return track

    def translation_caption_track(self, language: str) -> CaptionTrack | None:
        return next(
            (
                item
                for item in self.caption_tracks
                if item.kind == "translation" and item.language == language
            ),
            None,
        )

    def refresh_caption_track_view(self) -> None:
        track = self.caption_track()
        if track is None:
            self.cues = []
            self.findings = []
            self.exports = []
            return
        self.cues = [cue.model_copy(deep=True) for cue in track.cues]
        self.findings = [finding.model_copy(deep=True) for finding in track.findings]
        self.exports = [artifact.model_copy(deep=True) for artifact in track.exports]

    def sync_active_caption_track(self) -> None:
        track = self.caption_track()
        if track is None:
            return
        cues = [cue.model_copy(deep=True) for cue in self.cues]
        findings = [finding.model_copy(deep=True) for finding in self.findings]
        exports = [artifact.model_copy(deep=True) for artifact in self.exports]
        if track.cues != cues or track.findings != findings or track.exports != exports:
            track.cues = cues
            track.findings = findings
            track.exports = exports
            track.updated_at = utc_now()

    def activate_caption_track(self, track_id: str) -> CaptionTrack:
        track = self.caption_track(track_id)
        if track is None:
            raise KeyError(track_id)
        self.sync_active_caption_track()
        self.active_caption_track_id = track.id
        self.refresh_caption_track_view()
        return track

    def mark_translation_tracks_stale(self) -> None:
        for track in self.caption_tracks:
            if track.kind == "translation" and track.cues:
                track.review_state = "needs_update"
                track.updated_at = utc_now()

    @field_validator("speaker_names")
    @classmethod
    def valid_speaker_names''',
)

# Migrate old single-track projects without losing any cue, finding, or export state.
replace_once(
    "src/accessible_caption_studio/migrations.py",
    'from typing import Any\n',
    'from typing import Any\nfrom uuid import uuid4\n',
)
replace_once(
    "src/accessible_caption_studio/migrations.py",
    'CURRENT_PROJECT_SCHEMA_VERSION = 3',
    'CURRENT_PROJECT_SCHEMA_VERSION = 4',
)
replace_once(
    "src/accessible_caption_studio/migrations.py",
    '''        if version == 2:\n            data.setdefault("transcription_language", "en")\n            data.setdefault("sdh_mode", "full")\n            data["schema_version"] = 3\n            version = 3\n            changed = True\n            continue\n        raise ValueError''',
    '''        if version == 2:
            data.setdefault("transcription_language", "en")
            data.setdefault("sdh_mode", "full")
            data["schema_version"] = 3
            version = 3
            changed = True
            continue
        if version == 3:
            spoken_language = str(data.get("transcription_language") or "en")
            original_language = spoken_language if spoken_language != "auto" else "und"
            track_id = uuid4().hex
            data.setdefault("spoken_language", spoken_language)
            data.setdefault("detected_language", None)
            data.setdefault("requested_caption_languages", [])
            data["caption_tracks"] = [
                {
                    "id": track_id,
                    "language": original_language,
                    "kind": "original",
                    "source_track_id": None,
                    "source_language": None,
                    "review_state": "unreviewed",
                    "cues": deepcopy(data.get("cues", []) or []),
                    "findings": deepcopy(data.get("findings", []) or []),
                    "exports": deepcopy(data.get("exports", []) or []),
                    "translation_model": None,
                }
            ]
            data["active_caption_track_id"] = track_id
            data["schema_version"] = 4
            version = 4
            changed = True
            continue
        raise ValueError''',
)

# Persist whichever track the legacy editor currently exposes.
replace_once(
    "src/accessible_caption_studio/storage.py",
    '''        with self._lock:\n            project.schema_version = CURRENT_PROJECT_SCHEMA_VERSION\n''',
    '''        with self._lock:
            project.sync_active_caption_track()
            project.schema_version = CURRENT_PROJECT_SCHEMA_VERSION
''',
)
replace_once(
    "src/accessible_caption_studio/storage.py",
    '''        duplicate.exports = []\n        duplicate.latest_job_id = None\n''',
    '''        duplicate.exports = []
        for track in duplicate.caption_tracks:
            track.exports = []
        duplicate.refresh_caption_track_view()
        duplicate.latest_job_id = None
''',
)

# Capture Whisper's detected language when Auto-detect is selected.
replace_once(
    "src/accessible_caption_studio/whisper_worker.py",
    '''    model_name: str = "distil-large-v3",\n    language: str | None = None,\n) -> None:\n''',
    '''    model_name: str = "distil-large-v3",
    language: str | None = None,
    metadata_output_path: Path | None = None,
) -> None:
''',
)
replace_once(
    "src/accessible_caption_studio/whisper_worker.py",
    '''    words: list[dict[str, object]] = []\n    for interval in passes:\n''',
    '''    words: list[dict[str, object]] = []
    detected_language: str | None = None
    detected_probability: float | None = None
    for interval in passes:
''',
)
replace_once(
    "src/accessible_caption_studio/whisper_worker.py",
    '''        segments, _ = model.transcribe(\n            str(audio_path),\n            word_timestamps=True,\n            language=language,\n            vad_filter=False,\n            beam_size=5,\n            no_speech_threshold=0.8,\n            condition_on_previous_text=interval is None,\n            initial_prompt=None,\n            temperature=0.0,\n            clip_timestamps=clip or "0",\n        )\n        for segment in segments:\n''',
    '''        segments, info = model.transcribe(
            str(audio_path),
            word_timestamps=True,
            language=language,
            vad_filter=False,
            beam_size=5,
            no_speech_threshold=0.8,
            condition_on_previous_text=interval is None,
            initial_prompt=None,
            temperature=0.0,
            clip_timestamps=clip or "0",
        )
        if detected_language is None:
            detected_language = getattr(info, "language", None)
            probability = getattr(info, "language_probability", None)
            detected_probability = float(probability) if probability is not None else None
        for segment in segments:
''',
)
replace_once(
    "src/accessible_caption_studio/whisper_worker.py",
    '''    temporary = output_path.with_suffix(".partial.json")\n    temporary.write_text(json.dumps(words), encoding="utf-8")\n    temporary.replace(output_path)\n''',
    '''    temporary = output_path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(words), encoding="utf-8")
    temporary.replace(output_path)
    if metadata_output_path:
        metadata_temporary = metadata_output_path.with_suffix(".partial.json")
        metadata_temporary.write_text(
            json.dumps(
                {
                    "language": detected_language,
                    "language_probability": detected_probability,
                }
            ),
            encoding="utf-8",
        )
        metadata_temporary.replace(metadata_output_path)
''',
)
replace_once(
    "src/accessible_caption_studio/whisper_worker.py",
    '''    parser.add_argument("--language")\n    parser.add_argument("--vad-only", action="store_true")\n''',
    '''    parser.add_argument("--language")
    parser.add_argument("--metadata-output", type=Path)
    parser.add_argument("--vad-only", action="store_true")
''',
)
replace_once(
    "src/accessible_caption_studio/whisper_worker.py",
    '''            arguments.model,\n            arguments.language,\n        )\n''',
    '''            arguments.model,
            arguments.language,
            arguments.metadata_output,
        )
''',
)

replace_once(
    "src/accessible_caption_studio/enhanced_analyzer.py",
    '''        self.transcription_language = language if language else "en"\n        self.sdh_mode = sdh_mode if sdh_mode in {"off", "conservative", "full"} else "full"\n''',
    '''        self.transcription_language = language if language else "en"
        self.detected_language: str | None = None
        self.detected_language_probability: float | None = None
        self.sdh_mode = sdh_mode if sdh_mode in {"off", "conservative", "full"} else "full"
''',
)
replace_once(
    "src/accessible_caption_studio/enhanced_analyzer.py",
    '''    def _run_whisper(\n        self,\n        audio_path: Path,\n        output_path: Path,\n        intervals_path: Path | None = None,\n        progress: ProgressCallback | None = None,\n    ) -> subprocess.CompletedProcess[str]:\n        command = self._whisper_command(audio_path, output_path, intervals_path)\n''',
    '''    def _run_whisper(
        self,
        audio_path: Path,
        output_path: Path,
        intervals_path: Path | None = None,
        progress: ProgressCallback | None = None,
        metadata_output_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = self._whisper_command(audio_path, output_path, intervals_path)
        if metadata_output_path:
            command.extend(["--metadata-output", str(metadata_output_path)])
''',
)
replace_once(
    "src/accessible_caption_studio/enhanced_analyzer.py",
    '''    def transcribe(self, audio_path: Path) -> list[WordToken]:\n        if self._uses_english_model():\n            return super().transcribe(audio_path)\n        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:\n            output_path = Path(temporary_dir) / "words.json"\n            process = self._run_whisper(audio_path, output_path)\n''',
    '''    def transcribe(self, audio_path: Path) -> list[WordToken]:
        if self._uses_english_model():
            self.detected_language = "en"
            self.detected_language_probability = 1.0
            return super().transcribe(audio_path)
        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
            output_path = Path(temporary_dir) / "words.json"
            metadata_path = Path(temporary_dir) / "language.json"
            process = self._run_whisper(
                audio_path,
                output_path,
                metadata_output_path=metadata_path,
            )
''',
)
replace_once(
    "src/accessible_caption_studio/enhanced_analyzer.py",
    '''            try:\n                return [\n                    WordToken.model_validate(item)\n                    for item in json.loads(output_path.read_text(encoding="utf-8"))\n                ]\n            except (OSError, ValueError) as exc:\n''',
    '''            try:
                words = [
                    WordToken.model_validate(item)
                    for item in json.loads(output_path.read_text(encoding="utf-8"))
                ]
                if metadata_path.is_file():
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    detected = str(metadata.get("language") or "").strip().lower()
                    if detected:
                        self.detected_language = detected
                    probability = metadata.get("language_probability")
                    if probability is not None:
                        self.detected_language_probability = float(probability)
                return words
            except (OSError, ValueError) as exc:
''',
)

# Local translation implementation. The worker is short-lived so the large translation model
# does not remain resident in the web server after a translation job finishes.
write(
    "src/accessible_caption_studio/translation_worker.py",
    '''from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

MODEL_NAME = "facebook/m2m100_418M"


def translate(
    source_language: str,
    target_language: str,
    input_path: Path,
    output_path: Path,
    model_dir: Path,
) -> None:
    import torch
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    cache_dir = model_dir / "huggingface"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = M2M100Tokenizer.from_pretrained(MODEL_NAME, cache_dir=str(cache_dir))
    model = M2M100ForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        cache_dir=str(cache_dir),
    )
    model.to("cpu")
    model.eval()
    tokenizer.src_lang = source_language

    texts = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(texts, list) or not all(isinstance(item, str) for item in texts):
        raise ValueError("Translation input must be a list of caption strings")

    translated: list[str] = []
    forced_bos_token_id = tokenizer.get_lang_id(target_language)
    with torch.inference_mode():
        for start in range(0, len(texts), 8):
            batch = texts[start : start + 8]
            encoded = tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=256,
            )
            generated = model.generate(
                **encoded,
                forced_bos_token_id=forced_bos_token_id,
                max_length=256,
                num_beams=4,
                early_stopping=True,
            )
            translated.extend(
                tokenizer.batch_decode(generated, skip_special_tokens=True)
            )

    temporary = output_path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(translated, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_language")
    parser.add_argument("target_language")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("model_dir", type=Path)
    arguments = parser.parse_args()
    translate(
        arguments.source_language,
        arguments.target_language,
        arguments.input_path,
        arguments.output_path,
        arguments.model_dir,
    )


if __name__ == "__main__":
    main()
''',
)

write(
    "src/accessible_caption_studio/localization.py",
    '''from __future__ import annotations

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

        source_length = len(re.sub(r"\\s+", "", source_text))
        target_length = len(re.sub(r"\\s+", "", target_text))
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
    return re.sub(r"[^\\w]+", " ", value, flags=re.UNICODE).strip().casefold()


def _numbers(value: str) -> list[str]:
    return re.findall(r"(?<!\\w)\\d+(?:[.,]\\d+)?(?!\\w)", value)


def _proper_names_and_acronyms(value: str) -> list[str]:
    words = re.findall(r"\\b[^\\W\\d_][\\w'’-]*\\b", value, flags=re.UNICODE)
    protected: list[str] = []
    for index, word in enumerate(words):
        acronym = len(word) >= 2 and word.isupper()
        interior_name = index > 0 and len(word) >= 2 and word[:1].isupper() and word[1:].islower()
        if (acronym or interior_name) and word not in protected:
            protected.append(word)
    return protected
''',
)

write(
    "src/accessible_caption_studio/localization_routes.py",
    '''from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .errors import StudioError
from .jobs import JobManager
from .localization import create_translation_track, normalize_target_languages
from .models import AnalysisJob, Project
from .storage import ProjectStore


class CaptionTranslationRequest(BaseModel):
    target_languages: list[str] = Field(default_factory=list)
    replace_existing: bool = False


class CaptionTrackReviewRequest(BaseModel):
    review_state: Literal["unreviewed", "in_review", "reviewed"]


def start_translation_job(
    project_id: str,
    store: ProjectStore,
    jobs: JobManager,
    target_languages: list[str],
    *,
    replace_existing: bool = False,
) -> AnalysisJob:
    targets = normalize_target_languages(target_languages)
    if not targets:
        raise ValueError("Choose at least one caption language to translate")
    project = store.get(project_id)
    if not project.original_caption_track().cues:
        raise ValueError("Create or import original captions before translating")

    def target(job: Any, progress: Any) -> None:
        current = store.get(project_id)
        created: list[dict[str, str]] = []
        for index, language in enumerate(targets):
            progress(
                "Preparing translation",
                max(5, round(index / max(1, len(targets)) * 80)),
                f"Preparing {language} caption track",
            )
            track = create_translation_track(
                current,
                language,
                store.models_dir,
                progress,
                replace_existing=replace_existing,
            )
            created.append({"id": track.id, "language": track.language})
            store.save(current)
        job.result = {"type": "caption_translation", "tracks": created}
        progress("Translation ready", 98, "Translated caption tracks are ready for review")

    job = jobs.start(
        project_id,
        "caption-translation",
        target,
        parameters={
            "target_languages": targets,
            "replace_existing": replace_existing,
        },
    )
    project.latest_job_id = job.id
    store.save(project)
    return job


def register_localization_routes(
    app: FastAPI,
    store: ProjectStore,
    jobs: JobManager,
) -> None:
    @app.get("/api/projects/{project_id}/caption-tracks")
    def list_caption_tracks(project_id: str) -> list[dict[str, object]]:
        try:
            project = store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        return [track.model_dump(mode="json") for track in project.caption_tracks]

    @app.post("/api/projects/{project_id}/caption-tracks/translations", status_code=202)
    def translate_caption_tracks(
        project_id: str, request: CaptionTranslationRequest
    ) -> AnalysisJob:
        try:
            return start_translation_job(
                project_id,
                store,
                jobs,
                request.target_languages,
                replace_existing=request.replace_existing,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        except (ValueError, StudioError) as exc:
            message = exc.message if isinstance(exc, StudioError) else str(exc)
            raise HTTPException(status_code=400, detail=message) from exc

    @app.post("/api/projects/{project_id}/caption-tracks/{track_id}/activate")
    def activate_caption_track(project_id: str, track_id: str) -> Project:
        try:
            project = store.get(project_id)
            project.activate_caption_track(track_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Caption track not found") from exc
        return store.save(project, touch=False)

    @app.patch("/api/projects/{project_id}/caption-tracks/{track_id}")
    def update_caption_track(
        project_id: str,
        track_id: str,
        request: CaptionTrackReviewRequest,
    ) -> Project:
        try:
            project = store.get(project_id)
            track = project.caption_track(track_id)
            if track is None:
                raise KeyError(track_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Caption track not found") from exc
        track.review_state = request.review_state
        if track.id == project.active_caption_track_id:
            project.refresh_caption_track_view()
        return store.save(project)

    @app.delete(
        "/api/projects/{project_id}/caption-tracks/{track_id}",
        status_code=204,
    )
    def delete_caption_track(project_id: str, track_id: str) -> Response:
        try:
            project = store.get(project_id)
            track = project.caption_track(track_id)
            if track is None:
                raise KeyError(track_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Caption track not found") from exc
        if track.kind == "original":
            raise HTTPException(status_code=400, detail="The original caption track cannot be deleted")
        project.sync_active_caption_track()
        project.caption_tracks = [item for item in project.caption_tracks if item.id != track_id]
        if project.active_caption_track_id == track_id:
            project.active_caption_track_id = project.original_caption_track().id
        project.refresh_caption_track_view()
        store.save(project)
        return Response(status_code=204)
''',
)

# Model manager can preload/remove the translation model like every other local ML component.
replace_once(
    "src/accessible_caption_studio/model_management.py",
    '''    ("face-yunet-sface", "YuNet + SFace", "Anonymous local face detection and matching"),\n)\n''',
    '''    ("face-yunet-sface", "YuNet + SFace", "Anonymous local face detection and matching"),
    ("translation-m2m100", "M2M100 translation", "Local many-to-many caption translation model"),
)
''',
)
replace_once(
    "src/accessible_caption_studio/model_management.py",
    '''            "face-yunet-sface": [self.root / "opencv-face"],\n        }\n''',
    '''            "face-yunet-sface": [self.root / "opencv-face"],
            "translation-m2m100": [
                self.root / "huggingface" / "models--facebook--m2m100_418M"
            ],
        }
''',
)
replace_once(
    "src/accessible_caption_studio/model_worker.py",
    '''    if model_id == "face-yunet-sface":\n''',
    '''    if model_id == "translation-m2m100":
        from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

        model_name = "facebook/m2m100_418M"
        cache = str(root / "huggingface")
        M2M100Tokenizer.from_pretrained(model_name, cache_dir=cache)
        M2M100ForConditionalGeneration.from_pretrained(model_name, cache_dir=cache)
        return
    if model_id == "face-yunet-sface":
''',
)

# Web/API integration.
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''from .jobs import JobManager\n''',
    '''from .jobs import JobManager
from .localization import create_translation_track, normalize_target_languages
from .localization_routes import register_localization_routes, start_translation_job
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    sdh_mode: Literal["off", "conservative", "full"] = "full"\n\n\nclass ProjectUpdate''',
    '''    sdh_mode: Literal["off", "conservative", "full"] = "full"
    target_caption_languages: list[str] = Field(default_factory=list)


class ProjectUpdate''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        sdh_mode: Annotated[Literal["off", "conservative", "full"], Form()] = "full",\n    ) -> dict[str, Any]:\n        filename = safe_filename(media.filename or "media")\n''',
    '''        sdh_mode: Annotated[Literal["off", "conservative", "full"], Form()] = "full",
        target_caption_languages: Annotated[str, Form()] = "[]",
    ) -> dict[str, Any]:
        filename = safe_filename(media.filename or "media")
        targets = _parse_target_caption_languages(target_caption_languages)
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        project.transcription_quality = transcription_quality\n        project.transcription_language = transcription_language\n        project.sdh_mode = sdh_mode\n''',
    '''        project.transcription_quality = transcription_quality
        project.transcription_language = transcription_language
        project.spoken_language = transcription_language
        project.requested_caption_languages = targets
        project.sdh_mode = sdh_mode
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''                project.cues = parse_caption_file(caption_path)\n                project.findings = validate_cues(project.cues, project.media.duration)\n                caption_path.unlink(missing_ok=True)\n                store.save(project)\n                return {"project": project, "job": None}\n''',
    '''                project.cues = parse_caption_file(caption_path)
                project.findings = validate_cues(project.cues, project.media.duration)
                original = project.original_caption_track()
                original.language = (
                    transcription_language if transcription_language != "auto" else "und"
                )
                caption_path.unlink(missing_ok=True)
                store.save(project)
                job = (
                    start_translation_job(project.id, store, jobs, targets)
                    if targets
                    else None
                )
                return {"project": store.get(project.id), "job": job}
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        project.transcription_quality = request.transcription_quality\n        project.transcription_language = request.transcription_language\n        project.sdh_mode = request.sdh_mode\n''',
    '''        project.transcription_quality = request.transcription_quality
        project.transcription_language = request.transcription_language
        project.spoken_language = request.transcription_language
        project.requested_caption_languages = normalize_target_languages(
            request.target_caption_languages
        )
        project.sdh_mode = request.sdh_mode
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''                "transcription_language": request.transcription_language,\n                "sdh_mode": request.sdh_mode,\n''',
    '''                "transcription_language": request.transcription_language,
                "target_caption_languages": project.requested_caption_languages,
                "sdh_mode": request.sdh_mode,
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        if request.transcription_language is not None:\n            project.transcription_language = request.transcription_language\n''',
    '''        if request.transcription_language is not None:
            project.transcription_language = request.transcription_language
            project.spoken_language = request.transcription_language
''',
)

# Prevent source-analysis tools from writing source-language text into a translated track.
for anchor in (
    '    def analyze_overlap(project_id: str, request: OverlapRequest) -> Any:\n        project = _get_project(store, project_id)\n',
    '    def reanalyze_speakers(project_id: str, request: SpeakerReanalysisRequest) -> Any:\n        project = _get_project(store, project_id)\n',
    '    def repair_transcript(project_id: str) -> Any:\n        project = _get_project(store, project_id)\n',
):
    replacement = anchor + '        _require_original_caption_track(project)\n'
    replace_once("src/accessible_caption_studio/webapp.py", anchor, replacement)

replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    register_roadmap_routes(\n''',
    '''    register_localization_routes(app, store, jobs)

    register_roadmap_routes(
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    project = store.get(project_id)\n    if not project.media:\n        raise StudioError("media_not_ready", "Media is not ready for analysis.")\n''',
    '''    project = store.get(project_id)
    original_track = project.original_caption_track()
    if project.active_caption_track_id != original_track.id:
        project.activate_caption_track(original_track.id)
    if not project.media:
        raise StudioError("media_not_ready", "Media is not ready for analysis.")
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        project.transcription_quality,\n        project.transcription_language,\n        project.sdh_mode,\n''',
    '''        project.transcription_quality,
        project.spoken_language,
        project.sdh_mode,
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    project.sounds = sounds\n    project.cues = cues\n    project.findings = validate_cues(cues, project.media.duration)\n''',
    '''    project.sounds = sounds
    project.detected_language = getattr(analyzer, "detected_language", None)
    original_track = project.original_caption_track()
    original_track.language = (
        project.detected_language
        or (project.spoken_language if project.spoken_language != "auto" else "und")
    )
    project.cues = cues
    project.findings = validate_cues(cues, project.media.duration)
    project.mark_translation_tracks_stale()
''',
)
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''    store.save(project)\n    progress("Saving", 95, "Saving captions and accessibility findings")\n\n\ndef _normalized_caption_text''',
    '''    store.save(project)
    source_language = project.original_caption_track().language
    existing_translation_languages = {
        track.language for track in project.caption_tracks if track.kind == "translation"
    }
    for target_language in project.requested_caption_languages:
        if target_language == source_language or target_language in existing_translation_languages:
            continue
        try:
            progress(
                "Creating translated captions",
                96,
                f"Translating the original captions to {target_language}",
            )
            create_translation_track(
                project,
                target_language,
                store.models_dir,
                progress,
            )
            store.save(project)
            existing_translation_languages.add(target_language)
        except StudioError as exc:
            project.activate_caption_track(project.original_caption_track().id)
            project.findings.append(
                ValidationFinding(
                    code="translation_skipped",
                    message=f"Requested translation skipped: {exc.message}",
                    severity=Severity.WARNING,
                )
            )
            store.save(project)
    project.activate_caption_track(project.original_caption_track().id)
    store.save(project)
    progress("Saving", 99, "Saving caption tracks and accessibility findings")


def _parse_target_caption_languages(value: str) -> list[str]:
    try:
        raw = json.loads(value or "[]")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Caption languages are invalid") from exc
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="Caption languages are invalid")
    try:
        return normalize_target_languages([str(item) for item in raw])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_original_caption_track(project: Project) -> None:
    if project.active_caption_track().kind != "original":
        raise HTTPException(
            status_code=409,
            detail=(
                "This analysis tool works on the original spoken-language caption track. "
                "Switch to the Original track first."
            ),
        )


def _normalized_caption_text''',
)

# Preferences route keeps the compatibility alias and the explicit spoken-language field aligned.
replace_once(
    "src/accessible_caption_studio/roadmap.py",
    '''            project.transcription_language = request.transcription_language\n            project.sdh_mode = request.sdh_mode\n''',
    '''            project.transcription_language = request.transcription_language
            project.spoken_language = request.transcription_language
            project.sdh_mode = request.sdh_mode
''',
)
replace_once(
    "src/accessible_caption_studio/roadmap.py",
    '''                current.transcription_language = str(\n                    parameters.get("transcription_language") or current.transcription_language\n                )\n                mode = str(parameters.get("sdh_mode") or current.sdh_mode)\n''',
    '''                current.transcription_language = str(
                    parameters.get("transcription_language") or current.transcription_language
                )
                current.spoken_language = current.transcription_language
                requested = parameters.get("target_caption_languages") or []
                if isinstance(requested, list):
                    current.requested_caption_languages = [str(item) for item in requested]
                mode = str(parameters.get("sdh_mode") or current.sdh_mode)
''',
)

# Track-aware export filenames prevent one language from overwriting another, while keeping
# the existing filename behavior for ordinary single-track projects.
replace_once(
    "src/accessible_caption_studio/exports.py",
    '''def export_text(project: Project, project_dir: Path, format_name: str) -> ExportArtifact:\n''',
    '''def _caption_track_suffix(project: Project) -> str:
    if len(project.caption_tracks) <= 1:
        return ""
    language = safe_filename(project.active_caption_track().language, "und")
    return f" - {language}"


def export_text(project: Project, project_dir: Path, format_name: str) -> ExportArtifact:
''',
)
replace_once(
    "src/accessible_caption_studio/exports.py",
    '''    elif format_name == "ttml":\n        content, suffix = to_ttml(display_cues, project.transcription_language), ".ttml"\n''',
    '''    elif format_name == "ttml":
        content, suffix = to_ttml(display_cues, project.active_caption_track().language), ".ttml"
''',
)
replace_once(
    "src/accessible_caption_studio/exports.py",
    '''    destination = (\n        exports / f"{base}{suffix}"\n        if format_name == "report"\n        else exports / f"{base} - accessible captions{suffix}"\n    )\n''',
    '''    track_suffix = _caption_track_suffix(project)
    destination = (
        exports / f"{base}{track_suffix}{suffix}"
        if format_name == "report"
        else exports / f"{base}{track_suffix} - accessible captions{suffix}"
    )
''',
)
replace_once(
    "src/accessible_caption_studio/exports.py",
    '''    destination = exports / f"{base} - captioned.mp4"\n    partial = exports / f".{base} - captioned.partial.mp4"\n''',
    '''    track_suffix = _caption_track_suffix(project)
    destination = exports / f"{base}{track_suffix} - captioned.mp4"
    partial = exports / f".{base}{track_suffix} - captioned.partial.mp4"
''',
)

# Any caption-track artifact remains downloadable even after the user switches tracks.
replace_once(
    "src/accessible_caption_studio/webapp.py",
    '''        if not any(item.filename == safe for item in project.exports):\n            raise HTTPException(status_code=404, detail="Export not found")\n''',
    '''        all_exports = [
            item
            for track in project.caption_tracks
            for item in track.exports
        ]
        if not any(item.filename == safe for item in [*project.exports, *all_exports]):
            raise HTTPException(status_code=404, detail="Export not found")
''',
)

# Reports describe the active caption language, review state, and source spoken language.
replace_once(
    "src/accessible_caption_studio/reports.py",
    '''    findings = validate_cues(project.cues, duration)\n    findings.extend(caption_style_readability_findings(project.caption_style))\n''',
    '''    findings = list(project.findings)
    known = {(item.code, item.cue_id, item.message) for item in findings}
    for finding in validate_cues(project.cues, duration):
        key = (finding.code, finding.cue_id, finding.message)
        if key not in known:
            findings.append(finding)
            known.add(key)
    findings.extend(caption_style_readability_findings(project.caption_style))
''',
)
replace_once(
    "src/accessible_caption_studio/reports.py",
    '''    language = project.transcription_language\n    sdh = project.sdh_mode.title()\n''',
    '''    active_track = project.active_caption_track()
    language = active_track.language
    spoken_language = project.detected_language or project.spoken_language
    track_kind = active_track.kind.title()
    review_state = active_track.review_state.replace("_", " ").title()
    sdh = project.sdh_mode.title()
''',
)
replace_once(
    "src/accessible_caption_studio/reports.py",
    '''  <p>Transcription language: <strong>{html.escape(language)}</strong>. Sound-caption mode: <strong>{html.escape(sdh)}</strong>.</p>\n''',
    '''  <p>Caption track: <strong>{html.escape(language)}</strong> ({html.escape(track_kind)}). Review state: <strong>{html.escape(review_state)}</strong>. Spoken language: <strong>{html.escape(spoken_language)}</strong>. Sound-caption mode: <strong>{html.escape(sdh)}</strong>.</p>
''',
)

# Localization UI lives in final_batch.js so the mature editor can continue using its existing
# cue editor and preview against the active-track compatibility view.
replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''  const sdhStorageKey = "accessible-caption-sdh-mode";\n  const projectViewStorageKey = "accessible-caption-project-view";\n''',
    '''  const sdhStorageKey = "accessible-caption-sdh-mode";
  const captionLanguagesStorageKey = "accessible-caption-target-languages";
  const projectViewStorageKey = "accessible-caption-project-view";
''',
)
replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''  function defaultPreferences() {\n    const language = readPreference(languageStorageKey, "en");\n    const sdhMode = readPreference(sdhStorageKey, "full");\n    return {\n      transcription_language: languages.some(([code]) => code === language) ? language : "en",\n      sdh_mode: sdhModes.some(([code]) => code === sdhMode) ? sdhMode : "full",\n    };\n  }\n''',
    '''  function targetCaptionLanguages() {
    try {
      const parsed = JSON.parse(readPreference(captionLanguagesStorageKey, "[]"));
      if (!Array.isArray(parsed)) return [];
      return [...new Set(parsed.map(String))].filter((code) => code !== "auto" && languages.some(([value]) => value === code));
    } catch (_) { return []; }
  }
  function defaultPreferences() {
    const language = readPreference(languageStorageKey, "en");
    const sdhMode = readPreference(sdhStorageKey, "full");
    return {
      transcription_language: languages.some(([code]) => code === language) ? language : "en",
      target_caption_languages: targetCaptionLanguages(),
      sdh_mode: sdhModes.some(([code]) => code === sdhMode) ? sdhMode : "full",
    };
  }
''',
)
replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''      if (!init.body.has("transcription_language")) init.body.set("transcription_language", preferences.transcription_language);\n      if (!init.body.has("sdh_mode")) init.body.set("sdh_mode", preferences.sdh_mode);\n''',
    '''      if (!init.body.has("transcription_language")) init.body.set("transcription_language", preferences.transcription_language);
      if (!init.body.has("target_caption_languages")) init.body.set("target_caption_languages", JSON.stringify(preferences.target_caption_languages));
      if (!init.body.has("sdh_mode")) init.body.set("sdh_mode", preferences.sdh_mode);
''',
)
replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''        body.transcription_language ??= preferences.transcription_language;\n        body.sdh_mode ??= preferences.sdh_mode;\n''',
    '''        body.transcription_language ??= preferences.transcription_language;
        body.target_caption_languages ??= preferences.target_caption_languages;
        body.sdh_mode ??= preferences.sdh_mode;
''',
)

start = read("src/accessible_caption_studio/web/final_batch.js").index("  function installImportOptions() {")
end = read("src/accessible_caption_studio/web/final_batch.js").index("  function installProjectPreferenceDialog() {")
content = read("src/accessible_caption_studio/web/final_batch.js")
new_import_options = '''  function renderTargetLanguageChips(details, targets) {
    const container = details.querySelector("#defaultCaptionLanguageChips");
    if (!container) return;
    container.replaceChildren();
    targets.forEach((code) => {
      const chip = document.createElement("span");
      chip.className = "caption-language-chip";
      const text = document.createElement("span");
      text.textContent = languageLabel(code);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${languageLabel(code)} translation`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        const next = targets.filter((item) => item !== code);
        writePreference(captionLanguagesStorageKey, JSON.stringify(next));
        renderTargetLanguageChips(details, next);
        updateImportOptionsSummary(details, next);
      });
      chip.append(text, remove);
      container.append(chip);
    });
    const empty = details.querySelector("#defaultCaptionLanguageEmpty");
    if (empty) empty.hidden = targets.length > 0;
  }

  function updateImportOptionsSummary(details, targets = targetCaptionLanguages()) {
    const spoken = details.querySelector("#defaultTranscriptionLanguage")?.value || "en";
    const sdh = details.querySelector("#defaultSdhMode")?.value || "full";
    const translationCopy = targets.length ? ` · +${targets.length} translation${targets.length === 1 ? "" : "s"}` : "";
    details.querySelector("#captioningOptionsSummary").textContent = `${languageLabel(spoken)}${translationCopy} · ${sdhLabel(sdh)}`;
  }

  function installImportOptions() {
    if (document.querySelector("#captioningOptions")) return;
    const tabs = document.querySelector(".import-card .tabs");
    if (!tabs) return;
    const details = document.createElement("details");
    details.id = "captioningOptions";
    details.className = "captioning-options";
    details.innerHTML = `
      <summary>Captioning options <span id="captioningOptionsSummary"></span></summary>
      <div class="captioning-options-grid">
        <label for="defaultTranscriptionLanguage">Spoken language<select id="defaultTranscriptionLanguage">${optionMarkup(languages)}</select></label>
        <label for="defaultSdhMode">Sound captions<select id="defaultSdhMode">${optionMarkup(sdhModes)}</select></label>
        <div class="caption-target-picker">
          <label for="defaultTargetCaptionLanguage">Add translated caption track
            <select id="defaultTargetCaptionLanguage">
              <option value="">Choose a language…</option>
              ${optionMarkup(languages.filter(([code]) => code !== "auto"))}
            </select>
          </label>
          <div id="defaultCaptionLanguageChips" class="caption-language-chips" aria-live="polite"></div>
          <p id="defaultCaptionLanguageEmpty" class="caption-target-empty">Original-language captions only.</p>
        </div>
        <p class="captioning-options-note">The original spoken-language captions are always kept. Requested translations are created as separate editable tracks with the local M2M100 model; the translation model downloads only when first needed.</p>
      </div>`;
    tabs.after(details);
    const preferences = defaultPreferences();
    details.querySelector("#defaultTranscriptionLanguage").value = preferences.transcription_language;
    details.querySelector("#defaultSdhMode").value = preferences.sdh_mode;
    let targets = preferences.target_caption_languages.filter((code) => code !== preferences.transcription_language);
    writePreference(captionLanguagesStorageKey, JSON.stringify(targets));
    renderTargetLanguageChips(details, targets);
    const update = () => {
      const language = details.querySelector("#defaultTranscriptionLanguage").value;
      const sdh = details.querySelector("#defaultSdhMode").value;
      targets = targetCaptionLanguages().filter((code) => code !== language);
      writePreference(languageStorageKey, language);
      writePreference(sdhStorageKey, sdh);
      writePreference(captionLanguagesStorageKey, JSON.stringify(targets));
      renderTargetLanguageChips(details, targets);
      updateImportOptionsSummary(details, targets);
    };
    details.querySelector("#defaultTranscriptionLanguage").addEventListener("change", update);
    details.querySelector("#defaultSdhMode").addEventListener("change", update);
    details.querySelector("#defaultTargetCaptionLanguage").addEventListener("change", (event) => {
      const code = event.target.value;
      event.target.value = "";
      if (!code) return;
      const spoken = details.querySelector("#defaultTranscriptionLanguage").value;
      if (code === spoken) {
        toast("The original caption track already uses the spoken language.");
        return;
      }
      targets = [...new Set([...targetCaptionLanguages(), code])];
      writePreference(captionLanguagesStorageKey, JSON.stringify(targets));
      renderTargetLanguageChips(details, targets);
      updateImportOptionsSummary(details, targets);
    });
    updateImportOptionsSummary(details, targets);
  }

'''
write("src/accessible_caption_studio/web/final_batch.js", content[:start] + new_import_options + content[end:])
replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''<label for="projectTranscriptionLanguage">Language<select id="projectTranscriptionLanguage">${optionMarkup(languages)}</select></label>''',
    '''<label for="projectTranscriptionLanguage">Spoken language<select id="projectTranscriptionLanguage">${optionMarkup(languages)}</select></label>''',
)
replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''<p class="field-note">These options are saved with this project. Run analysis again after changing them to regenerate automatic captions.</p>''',
    '''<p class="field-note">These options control the original spoken-language transcription. Run analysis again after changing them; existing translated tracks are preserved and marked for review.</p>''',
)

replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''      .export-grid [data-export="report"] { border-color:color-mix(in srgb,var(--blue) 28%,var(--line)); }\n''',
    '''      .export-grid [data-export="report"] { border-color:color-mix(in srgb,var(--blue) 28%,var(--line)); }
      .caption-target-picker { grid-column:1/-1; display:grid; gap:.45rem; padding:.65rem; border:1px solid var(--soft-line); border-radius:10px; background:var(--wash); }
      .caption-language-chips { display:flex; flex-wrap:wrap; gap:.4rem; }
      .caption-language-chip { display:inline-flex; align-items:center; gap:.35rem; min-height:30px; padding:.25rem .35rem .25rem .55rem; border:1px solid var(--line); border-radius:999px; background:var(--paper); font-size:.74rem; font-weight:750; }
      .caption-language-chip button { width:22px; height:22px; min-height:22px; padding:0; border:0; border-radius:50%; background:transparent; color:var(--muted); font:inherit; }
      .caption-target-empty { margin:0; color:var(--muted); font-size:.72rem; }
      .caption-track-bar { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:.75rem; margin:0 0 .75rem; padding:.75rem; border:1px solid var(--line); border-radius:11px; background:color-mix(in srgb,var(--wash) 68%,var(--paper)); }
      .caption-track-main { min-width:0; display:grid; grid-template-columns:minmax(190px,1fr) auto; align-items:end; gap:.65rem; }
      .caption-track-field { display:grid; gap:.28rem; min-width:0; font-size:.72rem; font-weight:800; color:var(--muted); }
      .caption-track-field select { width:100%; min-height:38px; border:1px solid #aeb9ce; border-radius:9px; padding:.45rem .6rem; color:var(--ink); background:var(--control); }
      .caption-track-status { display:inline-flex; align-items:center; min-height:30px; padding:.3rem .55rem; border-radius:999px; background:var(--paper); border:1px solid var(--soft-line); color:var(--muted); font-size:.7rem; font-weight:800; white-space:nowrap; }
      .caption-track-status.needs-update { color:#8a4b08; border-color:#e7c089; background:#fff7e8; }
      .caption-track-actions { display:flex; flex-wrap:wrap; align-items:end; justify-content:flex-end; gap:.45rem; }
      .caption-track-add { display:grid; grid-template-columns:minmax(150px,1fr) auto; gap:.4rem; align-items:end; }
      .caption-track-add select { min-height:36px; border:1px solid #aeb9ce; border-radius:9px; padding:.4rem .55rem; color:var(--ink); background:var(--control); }
      .caption-track-context { margin:.55rem 0 0; padding:.55rem .7rem; border-radius:8px; background:var(--wash); color:var(--muted); font-size:.75rem; }
      @media (max-width:760px) {
        .caption-track-bar { grid-template-columns:1fr; align-items:stretch; }
        .caption-track-main { grid-template-columns:1fr; align-items:stretch; }
        .caption-track-actions { justify-content:stretch; }
        .caption-track-add { width:100%; grid-template-columns:1fr auto; }
      }
''',
)

localization_ui = r'''
  function activeCaptionTrack(project = state.project) {
    if (!project) return null;
    return (project.caption_tracks || []).find((track) => track.id === project.active_caption_track_id)
      || (project.caption_tracks || [])[0]
      || null;
  }

  function captionTrackOptionLabel(track) {
    const kind = track.kind === "original" ? "Original" : "Translation";
    const review = track.kind === "translation" && track.review_state === "needs_update" ? " · needs update" : "";
    return `${languageLabel(track.language)} · ${kind}${review}`;
  }

  function captionTrackStatusLabel(track) {
    if (!track) return "";
    if (track.kind === "original") return "Original transcription";
    return ({
      reviewed: "Reviewed",
      in_review: "In review",
      needs_update: "Source changed · review again",
      unreviewed: "Needs review",
    })[track.review_state] || "Needs review";
  }

  function installCaptionTrackContext() {
    const panel = document.querySelector(".editor-panel");
    if (!panel) return null;
    let bar = document.querySelector("#captionTrackBar");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "captionTrackBar";
      bar.className = "caption-track-bar";
      panel.prepend(bar);
    }
    return bar;
  }

  function renderCaptionTrackContext() {
    const project = state.project;
    if (!project) return;
    const bar = installCaptionTrackContext();
    if (!bar) return;
    const tracks = project.caption_tracks || [];
    const active = activeCaptionTrack(project);
    const existingTargets = new Set(tracks.filter((track) => track.kind === "translation").map((track) => track.language));
    const sourceLanguage = tracks.find((track) => track.kind === "original")?.language || project.detected_language || project.spoken_language || "en";
    const availableTargets = languages.filter(([code]) => code !== "auto" && code !== sourceLanguage && !existingTargets.has(code));
    bar.innerHTML = `
      <div class="caption-track-main">
        <label class="caption-track-field" for="captionTrackSelect">Caption track
          <select id="captionTrackSelect" aria-label="Caption track"></select>
        </label>
        <span id="captionTrackStatus" class="caption-track-status"></span>
      </div>
      <div class="caption-track-actions">
        <div class="caption-track-add">
          <label class="sr-only" for="captionTranslationLanguage">Add translated caption language</label>
          <select id="captionTranslationLanguage" aria-label="Add translated caption language">
            <option value="">Add translation…</option>
            ${optionMarkup(availableTargets)}
          </select>
          <button id="createCaptionTranslation" class="secondary editor-action" type="button">Create</button>
        </div>
        <button id="captionTrackReview" class="secondary editor-action" type="button"></button>
        <button id="regenerateCaptionTranslation" class="secondary editor-action" type="button">Regenerate</button>
        <button id="deleteCaptionTranslation" class="secondary editor-action" type="button">Delete translation</button>
      </div>`;
    const select = bar.querySelector("#captionTrackSelect");
    tracks.forEach((track) => {
      const option = document.createElement("option");
      option.value = track.id;
      option.textContent = captionTrackOptionLabel(track);
      select.append(option);
    });
    select.value = active?.id || "";
    const status = bar.querySelector("#captionTrackStatus");
    status.textContent = captionTrackStatusLabel(active);
    status.classList.toggle("needs-update", active?.review_state === "needs_update");

    const review = bar.querySelector("#captionTrackReview");
    const regenerate = bar.querySelector("#regenerateCaptionTranslation");
    const remove = bar.querySelector("#deleteCaptionTranslation");
    const translated = active?.kind === "translation";
    review.hidden = !translated;
    regenerate.hidden = !translated;
    remove.hidden = !translated;
    if (translated) {
      review.textContent = active.review_state === "reviewed" ? "Mark needs review" : "Mark reviewed";
      regenerate.hidden = active.review_state !== "needs_update";
    }

    const createButton = bar.querySelector("#createCaptionTranslation");
    const targetSelect = bar.querySelector("#captionTranslationLanguage");
    createButton.disabled = !availableTargets.length || !(tracks.find((track) => track.kind === "original")?.cues || project.cues || []).length;
    targetSelect.disabled = !availableTargets.length;
    select.addEventListener("change", () => switchCaptionTrack(select.value));
    createButton.addEventListener("click", () => createCaptionTranslation(false));
    review.addEventListener("click", toggleCaptionTrackReview);
    regenerate.addEventListener("click", () => createCaptionTranslation(true));
    remove.addEventListener("click", deleteCaptionTranslation);

    const sourceOnly = active?.kind === "translation";
    ["#improveTranscriptButton", "#redetectSpeakersButton"].forEach((selector) => {
      const button = document.querySelector(selector);
      if (!button) return;
      button.disabled = sourceOnly;
      button.title = sourceOnly ? "Switch to the Original caption track to use this source-analysis tool." : "";
    });
    document.querySelectorAll(".cue-actions button").forEach((button) => {
      if (/overlapping voices/i.test(button.textContent || "")) {
        button.disabled = sourceOnly;
        if (sourceOnly) button.title = "Switch to the Original caption track to analyze overlapping voices.";
      }
    });
    updateExportTrackContext();
  }

  async function switchCaptionTrack(trackId) {
    if (!state.project || !trackId || trackId === state.project.active_caption_track_id) return;
    try {
      await saveProject();
      state.project = await api(`/api/projects/${state.project.id}/caption-tracks/${encodeURIComponent(trackId)}/activate`, { method: "POST" });
      state.undo.length = 0;
      if (Array.isArray(state.redo)) state.redo.length = 0;
      renderProject();
      toast(`Now editing ${captionTrackOptionLabel(activeCaptionTrack())}.`);
    } catch (error) { toast(error.message, "error"); }
  }

  async function createCaptionTranslation(replaceExisting) {
    if (!state.project) return;
    const active = activeCaptionTrack();
    const target = replaceExisting
      ? active?.language
      : document.querySelector("#captionTranslationLanguage")?.value;
    if (!target) {
      toast("Choose a caption language to translate.");
      return;
    }
    try {
      await saveProject();
      const job = await api(`/api/projects/${state.project.id}/caption-tracks/translations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_languages: [target], replace_existing: Boolean(replaceExisting) }),
      });
      monitorJob(job, state.project.id, state.project.name);
      toast(`${replaceExisting ? "Regenerating" : "Creating"} ${languageLabel(target)} captions locally.`);
    } catch (error) { toast(error.message, "error"); }
  }

  async function toggleCaptionTrackReview() {
    const track = activeCaptionTrack();
    if (!state.project || track?.kind !== "translation") return;
    const reviewState = track.review_state === "reviewed" ? "unreviewed" : "reviewed";
    try {
      state.project = await api(`/api/projects/${state.project.id}/caption-tracks/${encodeURIComponent(track.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ review_state: reviewState }),
      });
      renderProject();
      toast(reviewState === "reviewed" ? "Translation marked reviewed." : "Translation marked for review.");
    } catch (error) { toast(error.message, "error"); }
  }

  async function deleteCaptionTranslation() {
    const track = activeCaptionTrack();
    if (!state.project || track?.kind !== "translation") return;
    if (!confirm(`Delete the ${languageLabel(track.language)} translated caption track? The original captions will be kept.`)) return;
    try {
      await api(`/api/projects/${state.project.id}/caption-tracks/${encodeURIComponent(track.id)}`, { method: "DELETE" });
      state.project = await api(`/api/projects/${state.project.id}`);
      renderProject();
      toast(`${languageLabel(track.language)} translation deleted.`);
    } catch (error) { toast(error.message, "error"); }
  }

  function updateExportTrackContext() {
    const dialog = document.querySelector("#exportDialog .dialog-card");
    if (!dialog || !state.project) return;
    let context = dialog.querySelector("#exportTrackContext");
    if (!context) {
      context = document.createElement("p");
      context.id = "exportTrackContext";
      context.className = "caption-track-context";
      const grid = dialog.querySelector(".export-grid");
      if (grid) grid.before(context);
      else dialog.append(context);
    }
    const track = activeCaptionTrack();
    context.textContent = track
      ? `Exporting ${languageLabel(track.language)} · ${track.kind === "original" ? "Original" : "Translation"} · ${captionTrackStatusLabel(track)}`
      : "Exporting the active caption track";
  }

  const previousRenderProjectLocalization = renderProject;
  renderProject = function renderProjectWithLocalization() {
    previousRenderProjectLocalization();
    renderCaptionTrackContext();
  };

  const previousOpenExportsLocalization = openExports;
  openExports = function openExportsWithTrackContext() {
    updateExportTrackContext();
    previousOpenExportsLocalization();
  };
'''
replace_once(
    "src/accessible_caption_studio/web/final_batch.js",
    '''  document.addEventListener("DOMContentLoaded", () => {\n''',
    localization_ui + '\n\n  document.addEventListener("DOMContentLoaded", () => {\n',
)

# Keep the new UI covered by browser regression tests without loading the translation model.
append_once(
    "tests/browser/test_browser_ui.py",
    "def test_localization_controls_distinguish_spoken_and_caption_languages",
    '''def test_localization_controls_distinguish_spoken_and_caption_languages(page: Page, studio_url: str) -> None:
    _open(page, studio_url)
    expect(page.get_by_label("Spoken language")).to_be_visible()
    expect(page.get_by_label("Add translated caption track")).to_be_visible()
    page.get_by_label("Spoken language").select_option("es")
    page.get_by_label("Add translated caption track").select_option("fr")
    expect(page.locator("#defaultCaptionLanguageChips")).to_contain_text("French")
    expect(page.locator("#captioningOptionsSummary")).to_contain_text("Spanish")
    expect(page.locator("#captioningOptionsSummary")).to_contain_text("+1 translation")
''',
)

# Core migration, switching, independent editing, QA and export behavior tests.
write(
    "tests/test_localization.py",
    '''from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from accessible_caption_studio.localization import (
    create_translation_track,
    translation_findings,
)
from accessible_caption_studio.migrations import (
    CURRENT_PROJECT_SCHEMA_VERSION,
    migrate_project_payload,
)
from accessible_caption_studio.models import CaptionCue, CaptionTrack, MediaAsset, Project
from accessible_caption_studio.storage import ProjectStore
from accessible_caption_studio.webapp import create_app


def test_schema_v3_migrates_single_caption_list_into_original_track() -> None:
    payload = {
        "schema_version": 3,
        "id": "a" * 32,
        "name": "Legacy Spanish",
        "transcription_language": "es",
        "cues": [
            {
                "id": "b" * 32,
                "start": 0,
                "end": 2,
                "text": "Hola mundo",
                "source": "transcription",
            }
        ],
        "findings": [],
        "exports": [],
    }
    migrated, changed = migrate_project_payload(payload)
    assert changed is True
    assert migrated["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 4
    assert migrated["spoken_language"] == "es"
    assert len(migrated["caption_tracks"]) == 1
    assert migrated["caption_tracks"][0]["kind"] == "original"
    assert migrated["caption_tracks"][0]["language"] == "es"
    assert migrated["caption_tracks"][0]["cues"][0]["text"] == "Hola mundo"

    project = Project.model_validate(migrated)
    assert project.cues[0].text == "Hola mundo"
    assert project.active_caption_track().id == project.original_caption_track().id


def test_track_switching_keeps_edits_independent(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Localization")
    project.cues = [CaptionCue(start=0, end=2, text="Hello world")]
    store.save(project)
    original = project.original_caption_track()
    translated = CaptionTrack(
        language="es",
        kind="translation",
        source_track_id=original.id,
        source_language="en",
        cues=[CaptionCue(start=0, end=2, text="Hola mundo")],
    )
    project.caption_tracks.append(translated)
    project.activate_caption_track(translated.id)
    store.save(project)

    loaded = store.get(project.id)
    loaded.cues[0].text = "Hola, mundo editado"
    store.save(loaded)
    loaded.activate_caption_track(original.id)
    store.save(loaded)
    assert loaded.cues[0].text == "Hello world"

    loaded.activate_caption_track(translated.id)
    assert loaded.cues[0].text == "Hola, mundo editado"


def test_translation_qa_flags_changed_numbers_names_and_caption_rules() -> None:
    source = [CaptionCue(start=0, end=1, text="Yesterday Alice paid 42 dollars.")]
    translated = [CaptionCue(start=0, end=1, text="Ayer Alicia pagó 24 dólares adicionales rápidamente.")]
    findings = translation_findings(source, translated, "en", "es", 3)
    codes = {finding.code for finding in findings}
    assert "translation_number_changed" in codes
    assert "translation_name_changed" in codes
    assert "reading_speed" in codes


def test_create_translation_track_preserves_source_timing_and_cues(monkeypatch, tmp_path: Path) -> None:
    project = Project(name="Translated")
    project.spoken_language = "en"
    project.transcription_language = "en"
    project.cues = [
        CaptionCue(start=1, end=3, text="Hello", speaker="Speaker 1"),
        CaptionCue(start=4, end=6, text="Goodbye", speaker="Speaker 2"),
    ]
    project.sync_active_caption_track()

    monkeypatch.setattr(
        "accessible_caption_studio.localization.translate_texts_local",
        lambda texts, source_language, target_language, model_dir, progress=None: [
            "Hola",
            "Adiós",
        ],
    )
    track = create_translation_track(project, "es", tmp_path / "models")
    assert track.kind == "translation"
    assert track.language == "es"
    assert [cue.text for cue in track.cues] == ["Hola", "Adiós"]
    assert [(cue.start, cue.end) for cue in track.cues] == [(1, 3), (4, 6)]
    assert [cue.text for cue in project.original_caption_track().cues] == ["Hello", "Goodbye"]


def test_api_switch_edit_validate_and_export_tracks_independently(tmp_path: Path) -> None:
    app = create_app(tmp_path / "storage")
    store = app.state.store
    project = store.create("Track export")
    project.media = MediaAsset(
        filename="audio.wav",
        stored_name="audio.wav",
        duration=10,
        has_video=False,
    )
    project.cues = [CaptionCue(start=0, end=2, text="Hello world")]
    store.save(project)
    project = store.get(project.id)
    original = project.original_caption_track()
    translated = CaptionTrack(
        language="es",
        kind="translation",
        source_track_id=original.id,
        source_language="en",
        cues=[CaptionCue(start=0, end=2, text="Hola mundo")],
    )
    project.caption_tracks.append(translated)
    store.save(project)
    client = TestClient(app)

    activated = client.post(
        f"/api/projects/{project.id}/caption-tracks/{translated.id}/activate"
    )
    assert activated.status_code == 200
    assert activated.json()["cues"][0]["text"] == "Hola mundo"

    edited = client.patch(
        f"/api/projects/{project.id}",
        json={"cues": [{"id": translated.cues[0].id, "start": 0, "end": 2, "text": "Hola editado", "source": "manual"}]},
    )
    assert edited.status_code == 200
    validated = client.post(f"/api/projects/{project.id}/validate")
    assert validated.status_code == 200
    spanish_export = client.post(f"/api/projects/{project.id}/exports/srt")
    assert spanish_export.status_code == 201
    spanish_filename = spanish_export.json()["filename"]
    assert " - es - " in spanish_filename

    original_response = client.post(
        f"/api/projects/{project.id}/caption-tracks/{original.id}/activate"
    )
    assert original_response.status_code == 200
    assert original_response.json()["cues"][0]["text"] == "Hello world"
    english_export = client.post(f"/api/projects/{project.id}/exports/srt")
    assert english_export.status_code == 201
    english_filename = english_export.json()["filename"]
    assert " - en - " in english_filename
    assert english_filename != spanish_filename

    # An artifact from another track stays downloadable after switching tracks.
    assert client.get(
        f"/api/projects/{project.id}/exports/{spanish_filename}"
    ).status_code == 200


def test_translation_job_creates_track_without_real_model(monkeypatch, tmp_path: Path) -> None:
    app = create_app(tmp_path / "storage")
    store = app.state.store
    project = store.create("Translation job")
    project.cues = [CaptionCue(start=0, end=2, text="Hello")]
    store.save(project)
    monkeypatch.setattr(
        "accessible_caption_studio.localization.translate_texts_local",
        lambda texts, source_language, target_language, model_dir, progress=None: ["Hola"],
    )
    client = TestClient(app)
    response = client.post(
        f"/api/projects/{project.id}/caption-tracks/translations",
        json={"target_languages": ["es"]},
    )
    assert response.status_code == 202
    job_id = response.json()["id"]
    for _ in range(100):
        job = app.state.jobs.get(project.id, job_id)
        if job.state.value not in {"queued", "running", "cancelling"}:
            break
        time.sleep(0.01)
    assert job.state.value == "completed"
    updated = store.get(project.id)
    spanish = updated.translation_caption_track("es")
    assert spanish is not None
    assert spanish.cues[0].text == "Hola"
    assert updated.original_caption_track().cues[0].text == "Hello"
''',
)

# Existing expectations that pin schema/model lists need the new feature reflected.
replace_once(
    "tests/test_final_roadmap.py",
    '''    assert migrated["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 3\n''',
    '''    assert migrated["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 4
''',
)
replace_once(
    "tests/test_final_roadmap.py",
    '''    assert "face-yunet-sface" in ids\n''',
    '''    assert "face-yunet-sface" in ids
    assert "translation-m2m100" in ids
''',
)

# Remove this one-time patch machinery from the product commit.
for temporary in (
    ROOT / "scripts" / "apply_localization_feature.py",
    ROOT / ".github" / "workflows" / "apply-localization-feature.yml",
    ROOT / ".github" / "localization-trigger.txt",
):
    temporary.unlink(missing_ok=True)

print("Applied multilingual caption localization feature")
