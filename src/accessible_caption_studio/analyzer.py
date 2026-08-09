from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
import time
import wave
from collections.abc import Callable, Sequence
from pathlib import Path

from .errors import SetupError, StudioError
from .models import CaptionCue, SoundEvent, SourceType, SpeakerTurn, WordToken
from .segmentation import segment_words, segment_words_by_speaker
from .transcription import detect_recovery_regions, merge_recovery_words

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
    def __init__(self, model_dir: Path, transcription_quality: str = "accurate") -> None:
        self.model_dir = model_dir
        self.transcription_quality = (
            transcription_quality if transcription_quality in {"fast", "accurate"} else "accurate"
        )
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.warnings: list[tuple[str, str]] = []

    def analyze(
        self,
        audio_path: Path,
        progress: ProgressCallback,
        expected_speaker_count: int | None = None,
    ) -> tuple[list[WordToken], list[SpeakerTurn], list[SoundEvent], list[CaptionCue]]:
        self._progress = progress
        progress(
            "Transcribing speech and singing",
            25,
            "Listening through the full audio with the local Whisper model",
        )
        words = self.transcribe(audio_path)
        try:
            words, recovery = self.recover_transcription(audio_path, words, progress)
            self.recovery_summary = recovery
        except StudioError as exc:
            self.recovery_summary = {"inserted": 0, "replaced": 0, "discarded": 0, "regions": []}
            self.warnings.append((exc.code, exc.message))
            progress("Transcript recovery skipped", 48, exc.message)
        cues = segment_words(words)
        progress(
            "Finding speakers",
            55,
            "Loading the free local speaker model (the first download may take a few minutes)",
        )
        try:
            speakers = self.diarize(audio_path, words, progress, expected_speaker_count)
        except StudioError as exc:
            speakers = []
            self.warnings.append((exc.code, exc.message))
            progress("Speaker labels skipped", 65, exc.message)
        if speakers:
            cues = segment_words_by_speaker(words, speakers)
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
            command = [
                    sys.executable,
                    "-m",
                    "accessible_caption_studio.whisper_worker",
                    "--model",
                    "small.en" if self.transcription_quality == "fast" else "distil-large-v3",
                    str(audio_path),
                    str(whisper_dir),
                    str(output_path),
                ]
            runner = getattr(getattr(self, "_progress", None), "run_process", None)
            process = runner(command) if runner else subprocess.run(
                command, capture_output=True, text=True, check=False
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

    def detect_speech_regions(
        self, audio_path: Path, progress: ProgressCallback | None = None
    ) -> list[tuple[float, float]]:
        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
            output_path = Path(temporary_dir) / "speech-regions.json"
            command = [
                sys.executable,
                "-m",
                "accessible_caption_studio.whisper_worker",
                "--vad-only",
                str(audio_path),
                str(self.model_dir / "whisper"),
                str(output_path),
            ]
            reporter = progress or getattr(self, "_progress", None)
            runner = getattr(reporter, "run_process", None)
            process = runner(command) if runner else subprocess.run(
                command, capture_output=True, text=True, check=False
            )
            if process.returncode or not output_path.is_file():
                return []
            try:
                return [
                    (float(item["start"]), float(item["end"]))
                    for item in json.loads(output_path.read_text(encoding="utf-8"))
                    if float(item["end"]) > float(item["start"])
                ]
            except (OSError, ValueError, KeyError):
                return []

    def recover_transcription(
        self,
        audio_path: Path,
        words: list[WordToken],
        progress: ProgressCallback | None = None,
        camera_cuts: list[float] | None = None,
    ) -> tuple[list[WordToken], dict[str, object]]:
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
        whisper_dir = self.model_dir / "whisper"
        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
            output_path = Path(temporary_dir) / "recovered-words.json"
            intervals_path = Path(temporary_dir) / "recovery-intervals.json"
            interval_payload = []
            for start, end in regions:
                interval_payload.append({"start": start, "end": end})
            intervals_path.write_text(
                json.dumps(interval_payload), encoding="utf-8"
            )
            command = [
                sys.executable,
                "-m",
                "accessible_caption_studio.whisper_worker",
                "--model",
                "small.en" if self.transcription_quality == "fast" else "distil-large-v3",
                str(audio_path),
                str(whisper_dir),
                str(output_path),
                "--intervals",
                str(intervals_path),
            ]
            runner = getattr(progress, "run_process", None)
            process = runner(command) if runner else subprocess.run(
                command, capture_output=True, text=True, check=False
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

    def diarize(
        self,
        audio_path: Path,
        words: list[WordToken],
        progress: ProgressCallback | None = None,
        expected_speaker_count: int | None = None,
    ) -> list[SpeakerTurn]:
        """Group speech windows with ECAPA in the managed worker process.

        The in-process branch below remains only for older integrations that do not
        supply a managed process runner. Normal analysis and reanalysis always use
        the cancellable ECAPA worker above.
        """

        runner = getattr(progress, "run_process", None)
        if runner:
            with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
                words_path = Path(temporary_dir) / "words.json"
                result_path = Path(temporary_dir) / "speakers.json"
                words_path.write_text(
                    json.dumps([word.model_dump(mode="json") for word in words]),
                    encoding="utf-8",
                )
                process = runner(
                    [
                        sys.executable,
                        "-m",
                        "accessible_caption_studio.speaker_worker",
                        str(audio_path),
                        str(self.model_dir),
                        str(words_path),
                        str(result_path),
                        str(expected_speaker_count or 0),
                    ]
                )
                if process.returncode:
                    details = (process.stderr or process.stdout or "").strip()
                    raise StudioError(
                        "diarization_failed",
                        f"Local speaker labeling could not finish: {details[-900:]}",
                    )
                payload = json.loads(result_path.read_text(encoding="utf-8"))
                items = payload.get("turns", payload) if isinstance(payload, dict) else payload
                self.voice_cluster_count = (
                    int(payload.get("voice_cluster_count", 0))
                    if isinstance(payload, dict)
                    else len({item.get("speaker") for item in items})
                )
                return [
                    SpeakerTurn.model_validate(item)
                    for item in items
                ]

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

            durations = [end - start for start, end in windows]
            labels = self._cluster_speaker_embeddings(
                embeddings, expected_count=expected_speaker_count, durations=durations
            )
            confidences = self._speaker_confidences(embeddings, labels, durations)
            labels = self._smooth_speaker_labels(labels, confidences, windows, words)
            labels = self._stable_labels(labels)
            confidences = self._speaker_confidences(embeddings, labels, durations)
            turns = [
                SpeakerTurn(
                    start=start,
                    end=end,
                    speaker=f"Speaker {label + 1}",
                    confidence=confidence,
                )
                for (start, end), label, confidence in zip(
                    windows, labels, confidences, strict=True
                )
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

    def analyze_overlap(
        self,
        audio_path: Path,
        start: float,
        end: float,
        reference_turns: list[SpeakerTurn],
        progress: ProgressCallback,
    ) -> tuple[list[list[WordToken]], list[str | None]]:
        with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
            output_path = Path(temporary_dir) / "overlap.json"
            references_path = Path(temporary_dir) / "references.json"
            references: dict[str, list[tuple[float, float]]] = {}
            for turn in reference_turns:
                if turn.end <= start or turn.start >= end:
                    continue
                references.setdefault(turn.speaker, []).append(
                    (max(start, turn.start), min(end, turn.end))
                )
            references_path.write_text(
                json.dumps(
                    [
                        {"speaker": speaker, "turns": turns}
                        for speaker, turns in references.items()
                    ]
                ),
                encoding="utf-8",
            )
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "accessible_caption_studio.overlap_worker",
                    str(audio_path),
                    str(start),
                    str(end),
                    str(self.model_dir),
                    str(references_path),
                    str(output_path),
                    str(getattr(self, "transcription_language", "en")),
                    str(getattr(self, "transcription_quality", "accurate")),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            register = getattr(progress, "register_process", None)
            unregister = getattr(progress, "unregister_process", None)
            if register:
                register(process)
            started = time.monotonic()
            try:
                while process.poll() is None:
                    elapsed = time.monotonic() - started
                    percent = min(82, 12 + round(elapsed / 3))
                    progress(
                        "Separating overlapping voices",
                        percent,
                        "Separating and transcribing two local voice tracks",
                    )
                    time.sleep(0.5)
            except BaseException:
                process.terminate()
                process.wait()
                raise
            finally:
                if unregister:
                    unregister(process)
            if process.returncode:
                details = process.stderr.read()[-1200:] if process.stderr else ""
                if "No module named 'speechbrain'" in details:
                    raise SetupError(
                        "overlap_model_not_installed",
                        "Optional overlapping-voice analysis is not installed. Relaunch setup.",
                    )
                raise StudioError(
                    "overlap_analysis_failed",
                    f"Overlapping voices could not be separated: {details}",
                )
            try:
                payload = json.loads(output_path.read_text(encoding="utf-8"))
                channels = [
                    [WordToken.model_validate(word) for word in channel]
                    for channel in payload["channels"]
                ]
                matches = [item if isinstance(item, str) else None for item in payload["matches"]]
            except (KeyError, OSError, ValueError) as exc:
                raise StudioError(
                    "overlap_analysis_failed", "The overlap model returned an unreadable result."
                ) from exc
        return self._deduplicate_overlap_channels(channels), matches[:2]

    @staticmethod
    def _deduplicate_overlap_channels(
        channels: list[list[WordToken]],
    ) -> list[list[WordToken]]:
        useful = [channel for channel in channels if channel]
        if len(useful) < 2:
            raise StudioError(
                "overlap_not_found", "Two distinct utterances were not found in this interval."
            )
        texts = [" ".join(word.text.lower().strip() for word in channel) for channel in useful]
        first_words = set(texts[0].split())
        second_words = set(texts[1].split())
        union = first_words | second_words
        similarity = len(first_words & second_words) / len(union) if union else 1.0
        if similarity >= 0.8:
            raise StudioError(
                "overlap_not_found",
                "The separated tracks contained the same speech, so no second voice was added.",
            )
        return useful[:2]

    @staticmethod
    def _speaker_windows(words: list[WordToken]) -> list[tuple[float, float]]:
        """Build non-overlapping voice samples without borrowing neighboring speech."""

        if not words:
            return []
        windows: list[tuple[float, float]] = []

        def append_window(window_start: float, window_end: float) -> None:
            duration = window_end - window_start
            if duration < 0.35:
                return
            windows.append((round(window_start, 3), round(window_end, 3)))

        start = words[0].start
        end = words[0].end
        for word in words[1:]:
            pause = word.start - end
            if pause > 0.55 or word.end - start > 4.0:
                append_window(start, end)
                start = word.start
            end = word.end
        append_window(start, end)
        return windows

    @staticmethod
    def _cluster_speaker_embeddings(
        embeddings: Sequence[Sequence[float]],
        expected_count: int | None = None,
        durations: Sequence[float] | None = None,
    ) -> list[int]:
        """Conservatively cluster clean anchors and assign short supporting samples."""

        vectors = [[float(value) for value in vector] for vector in embeddings]
        if len(vectors) == 0:
            return []
        normalized: list[list[float]] = []
        for vector in vectors:
            norm = math.sqrt(sum(value * value for value in vector))
            normalized.append([value / norm for value in vector] if norm else vector)
        sample_durations = list(durations or [2.0] * len(normalized))
        anchors = [index for index, duration in enumerate(sample_durations) if duration >= 1.5]
        requested = max(1, min(8, expected_count)) if expected_count is not None else None
        if requested and len(anchors) < requested:
            anchors = sorted(
                range(len(normalized)), key=lambda index: sample_durations[index], reverse=True
            )[:requested]
        if not anchors:
            anchors = [max(range(len(normalized)), key=lambda index: sample_durations[index])]

        def similarity(left: int, right: int) -> float:
            return sum(
                a * b for a, b in zip(normalized[left], normalized[right], strict=True)
            )

        def partition(count: int) -> list[list[int]]:
            clusters = [[index] for index in anchors]
            while len(clusters) > count:
                best_pair: tuple[int, int] | None = None
                best_score = -1.0
                for left in range(len(clusters)):
                    for right in range(left + 1, len(clusters)):
                        scores = [
                            similarity(a, b) for a in clusters[left] for b in clusters[right]
                        ]
                        score = sum(scores) / len(scores)
                        if score > best_score:
                            best_pair, best_score = (left, right), score
                if best_pair is None:
                    break
                left, right = best_pair
                clusters[left].extend(clusters.pop(right))
            return clusters

        def silhouette(clusters: list[list[int]]) -> float:
            if len(clusters) == 1:
                return 0.0
            membership = {
                index: group for group, cluster in enumerate(clusters) for index in cluster
            }
            scores: list[float] = []
            for index in anchors:
                own = clusters[membership[index]]
                within = (
                    sum(1.0 - similarity(index, other) for other in own if other != index)
                    / max(1, len(own) - 1)
                )
                outside = min(
                    sum(1.0 - similarity(index, other) for other in cluster) / len(cluster)
                    for group, cluster in enumerate(clusters)
                    if group != membership[index]
                )
                scores.append((outside - within) / max(outside, within, 1e-6))
            return sum(scores) / len(scores)

        if requested is not None:
            clusters = partition(min(requested, len(anchors)))
        else:
            clusters = partition(1)
            best_score = 0.0
            for count in range(2, min(8, len(anchors)) + 1):
                candidate = partition(count)
                supported = all(
                    len(cluster) >= 2
                    and sum(sample_durations[index] for index in cluster) >= 2.0
                    for cluster in candidate
                )
                if not supported:
                    continue
                score = silhouette(candidate) - 0.08 * (count - 1)
                if score > best_score + 0.05:
                    clusters, best_score = candidate, score

        centers: list[list[float]] = []
        for cluster in clusters:
            center = [
                sum(normalized[index][column] for index in cluster) / len(cluster)
                for column in range(len(normalized[0]))
            ]
            norm = math.sqrt(sum(value * value for value in center))
            centers.append([value / norm for value in center] if norm else center)
        labels = []
        for vector in normalized:
            scores = [sum(a * b for a, b in zip(vector, center, strict=True)) for center in centers]
            labels.append(max(range(len(scores)), key=scores.__getitem__))
        return LocalAnalyzer._stable_labels(labels)

    @staticmethod
    def _speaker_confidences(
        embeddings: Sequence[Sequence[float]],
        labels: list[int],
        durations: Sequence[float] | None = None,
    ) -> list[float]:
        if not embeddings:
            return []
        vectors = [[float(value) for value in vector] for vector in embeddings]
        centers: dict[int, list[float]] = {}
        for label in sorted(set(labels)):
            members = [
                vector
                for vector, item_label in zip(vectors, labels, strict=True)
                if item_label == label
            ]
            center = [sum(values) / len(values) for values in zip(*members, strict=True)]
            norm = math.sqrt(sum(value * value for value in center))
            centers[label] = [value / norm for value in center] if norm else center
        counts = {label: labels.count(label) for label in set(labels)}
        sample_durations = list(durations or [2.0] * len(vectors))
        confidences = []
        for vector, label, duration in zip(vectors, labels, sample_durations, strict=True):
            norm = math.sqrt(sum(value * value for value in vector))
            normalized = [value / norm for value in vector] if norm else vector
            own = sum(a * b for a, b in zip(normalized, centers[label], strict=True))
            alternatives = [
                sum(a * b for a, b in zip(normalized, center, strict=True))
                for other, center in centers.items()
                if other != label
            ]
            if alternatives:
                margin = own - max(alternatives)
                separation = max(0.0, min(1.0, (margin + 0.05) / 0.35))
            else:
                separation = 0.65
            quality = max(0.35, min(1.0, duration / 1.5))
            confidence = (0.35 + 0.65 * separation) * (0.75 + 0.25 * quality)
            if counts[label] == 1:
                confidence *= 0.48
            confidences.append(max(0.0, min(1.0, confidence)))
        return confidences

    @staticmethod
    def _smooth_speaker_labels(
        labels: list[int],
        confidences: Sequence[float],
        windows: Sequence[tuple[float, float]],
        words: Sequence[WordToken],
    ) -> list[int]:
        """Suppress weak identity flicker where continuous speech has no natural boundary."""

        smoothed = list(labels)
        for index in range(1, len(smoothed)):
            if smoothed[index] == smoothed[index - 1]:
                continue
            start, end = windows[index]
            previous_word = next(
                (word for word in reversed(words) if word.end <= start + 0.03), None
            )
            pause = start - windows[index - 1][1]
            sentence_end = bool(
                previous_word and re.search(r"[.!?][\"']?$", previous_word.text.strip())
            )
            natural_boundary = pause >= 0.35 or sentence_end
            strong_change = end - start >= 0.8 and confidences[index] >= 0.7
            if not natural_boundary and not strong_change:
                smoothed[index] = smoothed[index - 1]
        for index in range(1, len(smoothed) - 1):
            duration = windows[index][1] - windows[index][0]
            if smoothed[index - 1] == smoothed[index + 1] != smoothed[index] and duration < 0.8:
                smoothed[index] = smoothed[index - 1]
        return smoothed

    @staticmethod
    def _stable_labels(labels: Sequence[int]) -> list[int]:
        mapping: dict[int, int] = {}
        stable: list[int] = []
        for label in labels:
            if label not in mapping:
                mapping[label] = len(mapping)
            stable.append(mapping[label])
        return stable

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
                if turn.confidence is not None:
                    merged[-1].confidence = min(
                        merged[-1].confidence if merged[-1].confidence is not None else 1.0,
                        turn.confidence,
                    )
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
