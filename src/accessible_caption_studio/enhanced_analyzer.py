from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from .analyzer import LocalAnalyzer as BaseLocalAnalyzer
from .analyzer import ProgressCallback
from .errors import SetupError, StudioError
from .models import CaptionCue, SoundEvent, WordToken
from .transcription import detect_recovery_regions, merge_recovery_words


class LocalAnalyzer(BaseLocalAnalyzer):
    """Current analyzer plus multilingual Whisper and selectable SDH behavior."""

    def __init__(
        self,
        model_dir: Path,
        transcription_quality: str = "accurate",
        transcription_language: str = "en",
        sdh_mode: str = "full",
    ) -> None:
        super().__init__(model_dir, transcription_quality)
        language = str(transcription_language or "en").strip()
        self.transcription_language = language if language else "en"
        self.sdh_mode = sdh_mode if sdh_mode in {"off", "conservative", "full"} else "full"

    def _language_code(self) -> str | None:
        if self.transcription_language == "auto":
            return None
        return self.transcription_language.split("-", 1)[0].lower()

    def _uses_english_model(self) -> bool:
        return self._language_code() == "en"

    def _whisper_model_name(self) -> str:
        if self._uses_english_model():
            return "small.en" if self.transcription_quality == "fast" else "distil-large-v3"
        return "small" if self.transcription_quality == "fast" else "large-v3"

    def _whisper_command(
        self,
        audio_path: Path,
        output_path: Path,
        intervals_path: Path | None = None,
    ) -> list[str]:
        whisper_dir = self.model_dir / "whisper"
        whisper_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            "-m",
            "accessible_caption_studio.whisper_worker",
            "--model",
            self._whisper_model_name(),
        ]
        language = self._language_code()
        if language:
            command.extend(["--language", language])
        command.extend([str(audio_path), str(whisper_dir), str(output_path)])
        if intervals_path:
            command.extend(["--intervals", str(intervals_path)])
        return command

    def _run_whisper(
        self,
        audio_path: Path,
        output_path: Path,
        intervals_path: Path | None = None,
        progress: ProgressCallback | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = self._whisper_command(audio_path, output_path, intervals_path)
        reporter = progress or getattr(self, "_progress", None)
        runner = getattr(reporter, "run_process", None)
        return (
            runner(command)
            if runner
            else subprocess.run(command, capture_output=True, text=True, check=False)
        )

    def transcribe(self, audio_path: Path) -> list[WordToken]:
        if self._uses_english_model():
            return super().transcribe(audio_path)
        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
            output_path = Path(temporary_dir) / "words.json"
            process = self._run_whisper(audio_path, output_path)
            if process.returncode:
                details = (process.stderr or process.stdout or "").strip()
                if "No module named 'faster_whisper'" in details:
                    raise SetupError(
                        "ml_not_installed",
                        "Automatic transcription is not installed. Run setup from the launcher.",
                    )
                raise StudioError(
                    "transcription_failed",
                    f"Whisper transcription failed: {details[-1000:]}",
                )
            try:
                return [
                    WordToken.model_validate(item)
                    for item in json.loads(output_path.read_text(encoding="utf-8"))
                ]
            except (OSError, ValueError) as exc:
                raise StudioError(
                    "transcription_failed", "Whisper returned an unreadable result."
                ) from exc

    def recover_transcription(
        self,
        audio_path: Path,
        words: list[WordToken],
        progress: ProgressCallback | None = None,
        camera_cuts: list[float] | None = None,
    ) -> tuple[list[WordToken], dict[str, object]]:
        if self._uses_english_model():
            return super().recover_transcription(audio_path, words, progress, camera_cuts)

        speech_regions = self.detect_speech_regions(audio_path, progress)
        try:
            regions = detect_recovery_regions(
                audio_path,
                words,
                camera_cuts,
                speech_regions=speech_regions,
            )
        except (OSError, EOFError, wave.Error):
            regions = []
        empty: dict[str, object] = {
            "inserted": 0,
            "replaced": 0,
            "discarded": 0,
            "regions": regions,
        }
        if not regions:
            return words, empty
        if progress:
            progress(
                "Recovering missed dialogue",
                45,
                f"Rechecking {len(regions)} suspicious speech region"
                f"{'s' if len(regions) != 1 else ''}",
            )
        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
            output_path = Path(temporary_dir) / "recovered-words.json"
            intervals_path = Path(temporary_dir) / "recovery-intervals.json"
            intervals_path.write_text(
                json.dumps(
                    [{"start": start, "end": end} for start, end in regions]
                ),
                encoding="utf-8",
            )
            process = self._run_whisper(
                audio_path, output_path, intervals_path, progress
            )
            if process.returncode:
                detail = (process.stderr or process.stdout or "").strip()
                raise StudioError(
                    "transcript_recovery_failed",
                    "The primary transcript was kept because local dialogue recovery "
                    f"could not finish: {detail[-700:]}",
                )
            try:
                recovered = [
                    WordToken.model_validate(item)
                    for item in json.loads(output_path.read_text(encoding="utf-8"))
                ]
            except (OSError, ValueError) as exc:
                raise StudioError(
                    "transcript_recovery_failed",
                    "The primary transcript was kept because recovery returned unreadable data.",
                ) from exc
        merged, summary = merge_recovery_words(words, recovered)
        return merged, {**summary, "regions": regions}

    def detect_sounds(self, audio_path: Path) -> list[SoundEvent]:
        if self.sdh_mode == "off":
            return []
        events = super().detect_sounds(audio_path)
        if self.sdh_mode == "conservative":
            return [event for event in events if event.confidence >= 0.60]
        return events

    def sound_cues(
        self, events: list[SoundEvent], speech: list[CaptionCue]
    ) -> list[CaptionCue]:
        if self.sdh_mode == "off":
            return []
        if self.sdh_mode == "conservative":
            events = [event for event in events if event.confidence >= 0.60]
        return BaseLocalAnalyzer.sound_cues(events, speech)
