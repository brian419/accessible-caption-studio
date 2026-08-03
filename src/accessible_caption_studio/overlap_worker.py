"""Isolated two-speaker separation worker for short, user-selected intervals."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def separate_and_transcribe(
    audio_path: Path,
    start: float,
    end: float,
    model_dir: Path,
    references_path: Path,
    output_path: Path,
) -> None:
    import numpy as np
    import soundfile as sf
    import torch
    from speechbrain.inference.separation import SepformerSeparation

    audio, sample_rate = sf.read(str(audio_path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    clip = audio[round(start * sample_rate) : round(end * sample_rate)]
    if sample_rate != 16_000 or len(clip) < sample_rate // 2:
        raise ValueError("Overlap analysis needs at least half a second of 16 kHz audio.")

    separator = SepformerSeparation.from_hparams(
        source="speechbrain/sepformer-whamr16k",
        savedir=str(model_dir / "speechbrain" / "sepformer-whamr16k"),
        run_opts={"device": "cpu"},
    )
    with torch.no_grad():
        sources = separator.separate_batch(torch.from_numpy(clip).unsqueeze(0))

    matches: list[str | None] = [None, None]
    references = json.loads(references_path.read_text(encoding="utf-8"))
    if references:
        from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector

        model_name = "microsoft/wavlm-base-plus-sv"
        revision = "a0bfa70fc99be91689cfb6a9453c3cba66345df0"
        cache_dir = str(model_dir / "huggingface")
        extractor = Wav2Vec2FeatureExtractor.from_pretrained(
            model_name, revision=revision, cache_dir=cache_dir
        )
        voice_model = WavLMForXVector.from_pretrained(
            model_name,
            revision=revision,
            cache_dir=cache_dir,
            use_safetensors=True,
        )
        voice_model.eval()

        def embedding(samples: object) -> object:
            inputs = extractor(samples, sampling_rate=sample_rate, return_tensors="pt")
            with torch.no_grad():
                vector = voice_model(**inputs).embeddings[0]
            return torch.nn.functional.normalize(vector, dim=0)

        channel_embeddings = [
            embedding(sources[0, :, channel].detach().cpu().numpy())
            for channel in range(min(2, sources.shape[-1]))
        ]
        reference_embeddings = []
        for reference in references:
            pieces = [
                audio[
                    max(0, round(float(turn[0]) * sample_rate)) : round(
                        float(turn[1]) * sample_rate
                    )
                ]
                for turn in reference["turns"]
            ]
            useful_pieces = [piece for piece in pieces if len(piece)]
            if not useful_pieces:
                continue
            samples = np.concatenate(useful_pieces)
            if len(samples) >= sample_rate // 2:
                reference_embeddings.append((reference["speaker"], embedding(samples)))
        candidates = sorted(
            (
                (float(torch.dot(channel_vector, reference_vector)), channel, speaker)
                for channel, channel_vector in enumerate(channel_embeddings)
                for speaker, reference_vector in reference_embeddings
            ),
            reverse=True,
        )
        used_speakers: set[str] = set()
        for similarity, channel, speaker in candidates:
            if similarity < 0.65 or matches[channel] is not None or speaker in used_speakers:
                continue
            matches[channel] = speaker
            used_speakers.add(speaker)

    channels: list[list[dict[str, object]]] = []
    whisper_dir = model_dir / "whisper"
    with tempfile.TemporaryDirectory(dir=model_dir) as temporary:
        temporary_dir = Path(temporary)
        for channel in range(min(2, sources.shape[-1])):
            channel_path = temporary_dir / f"speaker-{channel + 1}.wav"
            words_path = temporary_dir / f"speaker-{channel + 1}.json"
            sf.write(channel_path, sources[0, :, channel].detach().cpu().numpy(), sample_rate)
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "accessible_caption_studio.whisper_worker",
                    str(channel_path),
                    str(whisper_dir),
                    str(words_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if process.returncode:
                raise RuntimeError((process.stderr or process.stdout)[-1000:])
            words = json.loads(words_path.read_text(encoding="utf-8"))
            for word in words:
                word["start"] = float(word["start"]) + start
                word["end"] = float(word["end"]) + start
            channels.append(words)

    partial = output_path.with_suffix(".partial.json")
    partial.write_text(json.dumps({"channels": channels, "matches": matches}), encoding="utf-8")
    partial.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path", type=Path)
    parser.add_argument("start", type=float)
    parser.add_argument("end", type=float)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("references_path", type=Path)
    parser.add_argument("output_path", type=Path)
    arguments = parser.parse_args()
    separate_and_transcribe(
        arguments.audio_path,
        arguments.start,
        arguments.end,
        arguments.model_dir,
        arguments.references_path,
        arguments.output_path,
    )


if __name__ == "__main__":
    main()
