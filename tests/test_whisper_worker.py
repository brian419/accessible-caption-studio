import json
import sys
from pathlib import Path
from types import SimpleNamespace

from accessible_caption_studio.whisper_worker import transcribe


def test_transcription_keeps_singing_instead_of_using_speech_vad(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    class FakeModel:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def transcribe(self, _audio_path, **options):
            captured.update(options)
            word = SimpleNamespace(word=" sung", start=1.0, end=1.5, probability=0.8)
            return iter([SimpleNamespace(words=[word])]), None

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeModel))
    output = tmp_path / "words.json"
    transcribe(tmp_path / "audio.wav", tmp_path / "models", output)

    assert captured["vad_filter"] is False
    assert captured["no_speech_threshold"] == 0.8
    assert captured["word_timestamps"] is True
    assert json.loads(output.read_text(encoding="utf-8"))[0]["text"] == "sung"
