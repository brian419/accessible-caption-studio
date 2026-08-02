from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from .errors import SetupError, StudioError
from .models import CaptionCue, SoundEvent, SourceType, SpeakerTurn, WordToken
from .segmentation import assign_speakers, segment_words

ProgressCallback = Callable[[str, int, str], None]

SOUND_LABELS = {
    "applause": "applause",
    "clapping": "applause",
    "laughter": "laughter",
    "laugh": "laughter",
    "door": "door closes",
    "knock": "knocking",
    "alarm": "alarm sounds",
    "siren": "siren",
    "glass": "glass breaks",
    "dog": "dog barks",
    "bark": "dog barks",
    "cat": "cat meows",
    "meow": "cat meows",
    "telephone": "phone rings",
    "ringtone": "phone rings",
    "music": "music",
    "singing": "singing",
    "thunder": "thunder",
    "gunshot": "gunshot",
    "explosion": "explosion",
    "crying": "crying",
    "sneeze": "sneezes",
    "cough": "coughing",
    "footstep": "footsteps",
    "cheering": "cheering",
    "vehicle horn": "car horn",
    "car horn": "car horn",
}


class LocalAnalyzer:
    def __init__(self, model_dir: Path, hf_token: str | None = None) -> None:
        self.model_dir = model_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.warnings: list[tuple[str, str]] = []

    def analyze(
        self, audio_path: Path, progress: ProgressCallback
    ) -> tuple[list[WordToken], list[SpeakerTurn], list[SoundEvent], list[CaptionCue]]:
        progress(
            "Transcribing speech and singing",
            25,
            "Listening through the full audio with the local Whisper model",
        )
        words = self.transcribe(audio_path)
        cues = segment_words(words)
        progress("Finding speakers", 55, "Assigning anonymous speaker turns")
        try:
            speakers = self.diarize(audio_path)
        except StudioError as exc:
            speakers = []
            self.warnings.append((exc.code, exc.message))
            progress("Speaker labels skipped", 65, exc.message)
        assign_speakers(cues, speakers)
        progress("Recognizing sounds", 75, "Looking for meaningful non-speech sounds")
        try:
            sounds = self.detect_sounds(audio_path)
        except StudioError as exc:
            sounds = []
            self.warnings.append((exc.code, exc.message))
            progress("Sound cues skipped", 85, exc.message)
        cues.extend(self.sound_cues(sounds, cues))
        cues.sort(key=lambda cue: (cue.start, cue.end, cue.source == SourceType.SOUND))
        return words, speakers, sounds, cues

    def transcribe(self, audio_path: Path) -> list[WordToken]:
        whisper_dir = self.model_dir / "whisper"
        whisper_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
            output_path = Path(temporary_dir) / "words.json"
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "accessible_caption_studio.whisper_worker",
                    str(audio_path),
                    str(whisper_dir),
                    str(output_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode:
                details = (process.stderr or process.stdout).strip()
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

    def diarize(self, audio_path: Path) -> list[SpeakerTurn]:
        if not self.hf_token:
            raise SetupError(
                "hf_token_required",
                "Speaker labeling needs a Hugging Face token with access to the pyannote model.",
            )
        try:
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise SetupError(
                "diarization_not_installed",
                "Speaker labeling dependencies are not installed.",
            ) from exc
        try:
            intel_mac = sys.platform == "darwin" and platform.machine() == "x86_64"
            if intel_mac:
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-3.1",
                    use_auth_token=self.hf_token,
                    cache_dir=str(self.model_dir / "huggingface"),
                )
            else:
                pipeline = Pipeline.from_pretrained(
                    "pyannote/speaker-diarization-community-1",
                    token=self.hf_token,
                    cache_dir=str(self.model_dir / "huggingface"),
                )
            if pipeline is None:
                raise SetupError(
                    "pyannote_access_required",
                    "Speaker labeling needs accepted pyannote model terms "
                    "and a valid Hugging Face read token.",
                )
            output = pipeline(str(audio_path))
            annotation = getattr(output, "exclusive_speaker_diarization", None)
            annotation = annotation or getattr(output, "speaker_diarization", output)
            raw: list[tuple[float, float, str]] = []
            for turn, _, label in annotation.itertracks(yield_label=True):
                raw.append((float(turn.start), float(turn.end), str(label)))
            label_order: dict[str, str] = {}
            for _, _, label in sorted(raw):
                label_order.setdefault(label, f"Speaker {len(label_order) + 1}")
            return [
                SpeakerTurn(start=start, end=end, speaker=label_order[label])
                for start, end, label in raw
            ]
        except SetupError:
            raise
        except Exception as exc:
            message = str(exc)
            if "gated" in message.lower() or "401" in message or "403" in message:
                raise SetupError(
                    "pyannote_access_required",
                    "Accept the pyannote model terms on Hugging Face, then save your token again.",
                ) from exc
            raise StudioError("diarization_failed", f"Speaker labeling failed: {exc}") from exc

    def detect_sounds(self, audio_path: Path) -> list[SoundEvent]:
        try:
            import soundfile as sf
            import torch
            from transformers import ASTForAudioClassification, AutoFeatureExtractor
        except ImportError as exc:
            raise SetupError(
                "sound_model_not_installed",
                "Sound recognition dependencies are not installed.",
            ) from exc
        model_name = "MIT/ast-finetuned-audioset-10-10-0.4593"
        try:
            audio, sample_rate = sf.read(str(audio_path), dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            cache_dir = str(self.model_dir / "huggingface")
            extractor = AutoFeatureExtractor.from_pretrained(model_name, cache_dir=cache_dir)
            model = ASTForAudioClassification.from_pretrained(model_name, cache_dir=cache_dir)
            model.eval()
            window_seconds, stride_seconds = 10, 5
            window_size, stride = sample_rate * window_seconds, sample_rate * stride_seconds
            events: list[SoundEvent] = []
            for start_sample in range(0, max(1, len(audio)), stride):
                clip = audio[start_sample : start_sample + window_size]
                if len(clip) < sample_rate:
                    break
                inputs = extractor(clip, sampling_rate=sample_rate, return_tensors="pt")
                with torch.no_grad():
                    probabilities = torch.sigmoid(model(**inputs).logits)[0]
                values, indices = probabilities.topk(min(8, len(probabilities)))
                for score, index in zip(values.tolist(), indices.tolist(), strict=True):
                    if score < 0.35:
                        continue
                    raw_label = model.config.id2label[index].lower()
                    label = self._accessible_label(raw_label)
                    if label:
                        start = start_sample / sample_rate
                        end = min(len(audio) / sample_rate, start + window_seconds)
                        events.append(
                            SoundEvent(label=label, start=start, end=end, confidence=score)
                        )
            return self.merge_sounds(events)
        except SetupError:
            raise
        except Exception as exc:
            raise StudioError("sound_detection_failed", f"Sound recognition failed: {exc}") from exc

    @staticmethod
    def _accessible_label(raw_label: str) -> str | None:
        raw_label = raw_label.lower()
        for needle, label in SOUND_LABELS.items():
            if re.search(rf"\b{re.escape(needle)}", raw_label):
                return label
        return None

    @staticmethod
    def merge_sounds(events: list[SoundEvent]) -> list[SoundEvent]:
        merged: list[SoundEvent] = []
        for event in sorted(events, key=lambda item: (item.label, item.start)):
            if merged and merged[-1].label == event.label and event.start <= merged[-1].end + 1:
                merged[-1].end = max(merged[-1].end, event.end)
                merged[-1].confidence = max(merged[-1].confidence, event.confidence)
            else:
                merged.append(event.model_copy())
        return sorted(merged, key=lambda item: item.start)

    @staticmethod
    def sound_cues(events: list[SoundEvent], speech: list[CaptionCue]) -> list[CaptionCue]:
        cues: list[CaptionCue] = []
        for event in events:
            start = event.start
            end = min(event.end, start + 3.0)
            overlaps = any(max(0, min(end, cue.end) - max(start, cue.start)) > 1 for cue in speech)
            if overlaps and event.confidence < 0.55:
                continue
            cues.append(
                CaptionCue(
                    start=start,
                    end=max(start + 1.5, end),
                    text=f"[{event.label}]",
                    source=SourceType.SOUND,
                    confidence=event.confidence,
                    sound_event_id=event.id,
                )
            )
        return cues
