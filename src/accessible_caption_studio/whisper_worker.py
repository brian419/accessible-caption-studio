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


def transcribe(audio_path: Path, model_dir: Path, output_path: Path) -> None:
    # CTranslate2 imports PyTorch only for optional model conversion helpers. Blocking that
    # import avoids loading PyTorch's second OpenMP runtime in the Whisper worker.
    sys.modules["torch"] = None
    from faster_whisper import WhisperModel

    model = WhisperModel(
        "small.en",
        device="cpu",
        compute_type="int8",
        download_root=str(model_dir),
    )
    segments, _ = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        # Silero VAD is trained around speech and can classify sustained singing as
        # non-speech. Whisper's own no-speech decision still suppresses genuine silence.
        vad_filter=False,
        beam_size=5,
        no_speech_threshold=0.8,
        condition_on_previous_text=True,
        temperature=0.0,
    )
    words: list[dict[str, object]] = []
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
                    }
                )
    temporary = output_path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(words), encoding="utf-8")
    temporary.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path", type=Path)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("output_path", type=Path)
    arguments = parser.parse_args()
    transcribe(arguments.audio_path, arguments.model_dir, arguments.output_path)


if __name__ == "__main__":
    main()
