from __future__ import annotations

import json
import sys
import wave
from array import array
from pathlib import Path
from typing import Any


def build_waveform_envelope(
    audio_path: Path,
    cache_path: Path | None = None,
    *,
    points: int = 1600,
) -> dict[str, Any]:
    """Return a normalized peak envelope for a mono 16-bit PCM WAV file."""
    points = max(100, min(int(points), 5000))
    source_stat = audio_path.stat()

    if cache_path and cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                cached.get("source_size") == source_stat.st_size
                and cached.get("source_mtime_ns") == source_stat.st_mtime_ns
                and cached.get("points") == points
            ):
                return cached
        except (OSError, ValueError, TypeError):
            pass

    with wave.open(str(audio_path), "rb") as source:
        channels = source.getnchannels()
        sample_width = source.getsampwidth()
        sample_rate = source.getframerate()
        frame_count = source.getnframes()
        if channels != 1 or sample_width != 2 or sample_rate <= 0 or frame_count <= 0:
            raise ValueError("Waveform source must be mono 16-bit PCM WAV audio")

        frames_per_bucket = max(1, (frame_count + points - 1) // points)
        peaks: list[float] = []
        while len(peaks) < points:
            raw = source.readframes(frames_per_bucket)
            if not raw:
                break
            samples = array("h")
            samples.frombytes(raw)
            if sys.byteorder == "big":
                samples.byteswap()
            peak = max((abs(sample) for sample in samples), default=0)
            peaks.append(round(min(1.0, peak / 32768.0), 5))

    payload: dict[str, Any] = {
        "duration": frame_count / sample_rate,
        "sample_rate": sample_rate,
        "points": points,
        "samples": peaks,
        "source_size": source_stat.st_size,
        "source_mtime_ns": source_stat.st_mtime_ns,
    }
    if cache_path:
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temporary.replace(cache_path)
    return payload
