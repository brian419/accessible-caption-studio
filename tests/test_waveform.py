from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from accessible_caption_studio.waveform import build_waveform_envelope


def _write_test_wave(path: Path, *, seconds: float = 1.0, sample_rate: int = 8000) -> None:
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            sample = int(math.sin(index / sample_rate * math.tau * 220) * 16000)
            frames.extend(struct.pack("<h", sample))
        target.writeframes(bytes(frames))


def test_build_waveform_envelope_and_reuse_cache(tmp_path: Path) -> None:
    source = tmp_path / "analysis.wav"
    cache = tmp_path / "waveform.json"
    _write_test_wave(source)

    first = build_waveform_envelope(source, cache, points=200)
    second = build_waveform_envelope(source, cache, points=200)

    assert first == second
    assert cache.is_file()
    assert first["duration"] == 1.0
    assert first["sample_rate"] == 8000
    assert 1 <= len(first["samples"]) <= 200
    assert max(first["samples"]) > 0.4
    assert all(0 <= value <= 1 for value in first["samples"])
