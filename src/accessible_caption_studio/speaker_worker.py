from __future__ import annotations

import json
import sys
from pathlib import Path

ECAPA_MODEL = "speechbrain/spkrec-ecapa-voxceleb"
ECAPA_REVISION = "0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"


def main() -> None:
    import soundfile as sf
    import torch

    # SpeechBrain 1.1 uses the device-aware torch.amp decorator added after
    # PyTorch 2.2. Intel Macs must stay on the final supported PyTorch 2.2
    # wheel, and this worker is CPU-only, so a direct CPU wrapper is equivalent.
    if not hasattr(torch.amp, "custom_fwd"):
        def compatible_custom_fwd(
            function=None, *, device_type: str, cast_inputs=None
        ):
            if function is None:
                return lambda wrapped: compatible_custom_fwd(
                    wrapped, device_type=device_type, cast_inputs=cast_inputs
                )
            if device_type == "cuda":
                return torch.cuda.amp.custom_fwd(
                    function, cast_inputs=cast_inputs
                )
            return function

        torch.amp.custom_fwd = compatible_custom_fwd

    from speechbrain.inference.classifiers import EncoderClassifier
    from speechbrain.utils.fetching import FetchConfig, LocalStrategy

    from .analyzer import LocalAnalyzer
    from .models import SpeakerTurn, WordToken

    audio_path, model_dir, words_path, result_path = map(Path, sys.argv[1:5])
    expected = int(sys.argv[5]) or None
    words = [
        WordToken.model_validate(item)
        for item in json.loads(words_path.read_text(encoding="utf-8"))
    ]
    windows = LocalAnalyzer._speaker_windows(words)
    if not windows:
        result_path.write_text(
            json.dumps({"engine": "ecapa", "voice_cluster_count": 0, "turns": []}),
            encoding="utf-8",
        )
        return

    audio, sample_rate = sf.read(str(audio_path), dtype="float32")
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    if sample_rate != 16_000:
        raise RuntimeError("ECAPA speaker analysis requires normalized 16 kHz audio.")

    savedir = model_dir / "ecapa-voxceleb"
    classifier = EncoderClassifier.from_hparams(
        source=ECAPA_MODEL,
        savedir=str(savedir),
        run_opts={"device": "cpu"},
        local_strategy=LocalStrategy.COPY,
        fetch_config=FetchConfig(revision=ECAPA_REVISION),
    )
    classifier.eval()
    embeddings: list[list[float]] = []
    with torch.no_grad():
        for start, end in windows:
            clip = audio[max(0, round(start * sample_rate)) : round(end * sample_rate)]
            signal = torch.from_numpy(clip).unsqueeze(0)
            vector = classifier.encode_batch(signal, normalize=True).reshape(-1)
            vector = torch.nn.functional.normalize(vector, dim=0)
            embeddings.append(vector.cpu().numpy().astype(float).tolist())

    durations = [end - start for start, end in windows]
    labels = LocalAnalyzer._cluster_speaker_embeddings(
        embeddings, expected_count=expected, durations=durations
    )
    confidences = LocalAnalyzer._speaker_confidences(embeddings, labels, durations)
    labels = LocalAnalyzer._smooth_speaker_labels(labels, confidences, windows, words)
    labels = LocalAnalyzer._stable_labels(labels)
    confidences = LocalAnalyzer._speaker_confidences(embeddings, labels, durations)
    turns = [
        SpeakerTurn(
            start=start,
            end=end,
            speaker=f"Speaker {label + 1}",
            confidence=confidence,
            audio_confidence=confidence,
            method="voice_only" if confidence >= 0.65 else "uncertain",
        )
        for (start, end), label, confidence in zip(
            windows, labels, confidences, strict=True
        )
    ]
    turns = LocalAnalyzer._merge_speaker_turns(turns)
    result_path.write_text(
        json.dumps(
            {
                "engine": "ecapa",
                "voice_cluster_count": len(set(labels)),
                "turns": [turn.model_dump(mode="json") for turn in turns],
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
