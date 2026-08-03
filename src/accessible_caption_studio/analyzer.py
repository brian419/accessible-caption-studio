from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
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
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self.model_dir.mkdir(parents=True, exist_ok=True)
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
        progress(
            "Finding speakers",
            55,
            "Loading the free local speaker model (the first download may take a few minutes)",
        )
        try:
            speakers = self.diarize(audio_path, words, progress)
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

    def diarize(
        self,
        audio_path: Path,
        words: list[WordToken],
        progress: ProgressCallback | None = None,
    ) -> list[SpeakerTurn]:
        """Group speech windows by voice using a public, token-free WavLM model."""

        try:
            import soundfile as sf
            import torch
            from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector
        except ImportError as exc:
            raise SetupError(
                "diarization_not_installed",
                "Speaker labeling dependencies are not installed.",
            ) from exc

        windows = self._speaker_windows(words)
        if not windows:
            return []

        model_name = "microsoft/wavlm-base-plus-sv"
        # This public revision includes safe-tensor weights and has no access form or token.
        model_revision = "a0bfa70fc99be91689cfb6a9453c3cba66345df0"
        try:
            cache_dir = str(self.model_dir / "huggingface")
            extractor = Wav2Vec2FeatureExtractor.from_pretrained(
                model_name, revision=model_revision, cache_dir=cache_dir
            )
            model = WavLMForXVector.from_pretrained(
                model_name,
                revision=model_revision,
                cache_dir=cache_dir,
                use_safetensors=True,
            )
            model.eval()
            audio, sample_rate = sf.read(str(audio_path), dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if sample_rate != 16_000:
                raise StudioError(
                    "speaker_audio_invalid",
                    "Speaker analysis expected the normalized 16 kHz audio track.",
                )

            embeddings: list[list[float]] = []
            for index, (start, end) in enumerate(windows):
                if progress:
                    percent = 57 + round(13 * index / max(1, len(windows)))
                    progress(
                        "Finding speakers",
                        percent,
                        f"Comparing voice sample {index + 1} of {len(windows)}",
                    )
                clip = audio[max(0, round(start * sample_rate)) : round(end * sample_rate)]
                inputs = extractor(clip, sampling_rate=sample_rate, return_tensors="pt")
                with torch.no_grad():
                    vector = model(**inputs).embeddings[0]
                    vector = torch.nn.functional.normalize(vector, dim=0)
                embeddings.append(vector.cpu().numpy().astype(float).tolist())

            labels = self._cluster_speaker_embeddings(embeddings)
            turns = [
                SpeakerTurn(start=start, end=end, speaker=f"Speaker {label + 1}")
                for (start, end), label in zip(windows, labels, strict=True)
            ]
            return self._merge_speaker_turns(turns)
        except Exception as exc:
            if isinstance(exc, StudioError):
                raise
            raise StudioError(
                "diarization_failed",
                "Local speaker labeling could not finish. Captions were still created. "
                f"Details: {exc}",
            ) from exc

    @staticmethod
    def _speaker_windows(words: list[WordToken]) -> list[tuple[float, float]]:
        """Build useful voice samples from Whisper speech timestamps."""

        if not words:
            return []
        windows: list[tuple[float, float]] = []
        start = words[0].start
        end = words[0].end
        for word in words[1:]:
            pause = word.start - end
            if pause > 0.75 or word.end - start > 4.0:
                if end - start >= 0.8:
                    windows.append((round(max(0.0, start - 0.1), 3), round(end + 0.1, 3)))
                start = word.start
            end = word.end
        if end - start >= 0.8:
            windows.append((round(max(0.0, start - 0.1), 3), round(end + 0.1, 3)))
        return windows

    @staticmethod
    def _cluster_speaker_embeddings(
        embeddings: Sequence[Sequence[float]], threshold: float = 0.72
    ) -> list[int]:
        """Online cosine clustering with stable order-of-appearance labels."""

        vectors = [[float(value) for value in vector] for vector in embeddings]
        if len(vectors) == 0:
            return []
        centers: list[list[float]] = []
        counts: list[int] = []
        labels: list[int] = []
        for vector in vectors:
            norm = math.sqrt(sum(value * value for value in vector))
            vector = [value / norm for value in vector] if norm else vector
            similarities = [
                sum(a * b for a, b in zip(vector, center, strict=True)) for center in centers
            ]
            if similarities and max(similarities) >= threshold:
                label = similarities.index(max(similarities))
                counts[label] += 1
                center = [
                    (old * (counts[label] - 1) + new) / counts[label]
                    for old, new in zip(centers[label], vector, strict=True)
                ]
                center_norm = math.sqrt(sum(value * value for value in center))
                centers[label] = (
                    [value / center_norm for value in center] if center_norm else center
                )
            else:
                label = len(centers)
                centers.append(vector)
                counts.append(1)
            labels.append(label)
        return labels

    @staticmethod
    def _merge_speaker_turns(turns: list[SpeakerTurn]) -> list[SpeakerTurn]:
        merged: list[SpeakerTurn] = []
        for turn in turns:
            if (
                merged
                and merged[-1].speaker == turn.speaker
                and turn.start <= merged[-1].end + 0.75
            ):
                merged[-1].end = max(merged[-1].end, turn.end)
            else:
                merged.append(turn.model_copy())
        return merged

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
