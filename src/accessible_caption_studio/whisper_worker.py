"""Isolated Whisper entry point.

Intel CTranslate2 and PyTorch packages can bundle different OpenMP runtimes. Whisper runs
in this short-lived process so its runtime never shares a process with diarization or
sound classification.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def transcribe(
    audio_path: Path,
    model_dir: Path,
    output_path: Path,
    intervals_path: Path | None = None,
    model_name: str = "distil-large-v3",
    language: str | None = None,
) -> None:
    # CTranslate2 imports PyTorch only for optional model conversion helpers. Blocking that
    # import avoids loading PyTorch's second OpenMP runtime in the Whisper worker.
    sys.modules["torch"] = None
    from faster_whisper import WhisperModel

    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
        download_root=str(model_dir),
    )
    intervals = None
    if intervals_path:
        intervals = json.loads(intervals_path.read_text(encoding="utf-8"))
    passes = intervals or [None]
    words: list[dict[str, object]] = []
    for interval in passes:
        if isinstance(interval, dict):
            clip = [float(interval["start"]), float(interval["end"])]
        else:
            clip = interval
        segments, _ = model.transcribe(
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
        for segment in segments:
            for word in segment.words or []:
                text = word.word.strip()
                if text:
                    words.append(
                        {
                            "text": text,
                            "start": max(0, float(word.start)),
                            "end": max(float(word.start), float(word.end)),
                            "confidence": float(word.probability),
                            "transcription_source": "recovery" if interval else "primary",
                        }
                    )
    temporary = output_path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(words), encoding="utf-8")
    temporary.replace(output_path)


def detect_speech(audio_path: Path, output_path: Path) -> None:
    from faster_whisper.audio import decode_audio
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio = decode_audio(str(audio_path), sampling_rate=16000)
    regions = get_speech_timestamps(
        audio,
        VadOptions(
            threshold=0.35,
            min_speech_duration_ms=120,
            max_speech_duration_s=15,
            min_silence_duration_ms=250,
            speech_pad_ms=250,
        ),
        sampling_rate=16000,
    )
    payload = [
        {"start": item["start"] / 16000, "end": item["end"] / 16000}
        for item in regions
    ]
    temporary = output_path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path", type=Path)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--intervals", type=Path)
    parser.add_argument(
        "--model",
        choices=("small.en", "distil-large-v3", "small", "large-v3"),
        default="distil-large-v3",
    )
    parser.add_argument("--language")
    parser.add_argument("--vad-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.vad_only:
        detect_speech(arguments.audio_path, arguments.output_path)
    else:
        transcribe(
            arguments.audio_path,
            arguments.model_dir,
            arguments.output_path,
            arguments.intervals,
            arguments.model,
            arguments.language,
        )


if __name__ == "__main__":
    main()
