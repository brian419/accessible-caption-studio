from __future__ import annotations

import argparse
from pathlib import Path


def _patch_speechbrain_torch() -> None:
    import torch

    if hasattr(torch.amp, "custom_fwd"):
        return

    def compatible_custom_fwd(function=None, *, device_type: str, cast_inputs=None):
        if function is None:
            return lambda wrapped: compatible_custom_fwd(
                wrapped, device_type=device_type, cast_inputs=cast_inputs
            )
        if device_type == "cuda":
            return torch.cuda.amp.custom_fwd(function, cast_inputs=cast_inputs)
        return function

    torch.amp.custom_fwd = compatible_custom_fwd


def install(model_id: str, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    whisper_models = {
        "whisper-en-fast": "small.en",
        "whisper-en-accurate": "distil-large-v3",
        "whisper-multilingual-fast": "small",
        "whisper-multilingual-accurate": "large-v3",
    }
    if model_id in whisper_models:
        from faster_whisper import WhisperModel

        WhisperModel(
            whisper_models[model_id],
            device="cpu",
            compute_type="int8",
            download_root=str(root / "whisper"),
        )
        return
    if model_id == "speaker-ecapa":
        _patch_speechbrain_torch()
        from speechbrain.inference.classifiers import EncoderClassifier
        from speechbrain.utils.fetching import FetchConfig, LocalStrategy

        EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=str(root / "ecapa-voxceleb"),
            run_opts={"device": "cpu"},
            local_strategy=LocalStrategy.COPY,
            fetch_config=FetchConfig(
                revision="0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"
            ),
        )
        return
    if model_id == "speaker-wavlm":
        from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector

        model_name = "microsoft/wavlm-base-plus-sv"
        revision = "a0bfa70fc99be91689cfb6a9453c3cba66345df0"
        cache = str(root / "huggingface")
        Wav2Vec2FeatureExtractor.from_pretrained(
            model_name, revision=revision, cache_dir=cache
        )
        WavLMForXVector.from_pretrained(
            model_name,
            revision=revision,
            cache_dir=cache,
            use_safetensors=True,
        )
        return
    if model_id == "sound-ast":
        from transformers import ASTForAudioClassification, AutoFeatureExtractor

        model_name = "MIT/ast-finetuned-audioset-10-10-0.4593"
        cache = str(root / "huggingface")
        AutoFeatureExtractor.from_pretrained(model_name, cache_dir=cache)
        ASTForAudioClassification.from_pretrained(model_name, cache_dir=cache)
        return
    if model_id == "overlap-sepformer":
        _patch_speechbrain_torch()
        from speechbrain.inference.separation import SepformerSeparation

        SepformerSeparation.from_hparams(
            source="speechbrain/sepformer-whamr16k",
            savedir=str(root / "speechbrain" / "sepformer-whamr16k"),
            run_opts={"device": "cpu"},
        )
        return
    if model_id == "translation-m2m100":
        from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

        from .translation_worker import MODEL_NAME, MODEL_REVISION

        cache = str(root / "huggingface")
        M2M100Tokenizer.from_pretrained(
            MODEL_NAME,
            revision=MODEL_REVISION,
            cache_dir=cache,
        )
        M2M100ForConditionalGeneration.from_pretrained(
            MODEL_NAME,
            revision=MODEL_REVISION,
            cache_dir=cache,
            use_safetensors=True,
            low_cpu_mem_usage=False,
        )
        return
    if model_id == "face-yunet-sface":
        from .visual_worker import (
            SFACE_NAME,
            SFACE_SHA256,
            YUNET_NAME,
            YUNET_SHA256,
            _ensure_model,
        )

        directory = root / "opencv-face"
        _ensure_model(directory, YUNET_NAME, "face_detection_yunet", YUNET_SHA256)
        _ensure_model(directory, SFACE_NAME, "face_recognition_sface", SFACE_SHA256)
        return
    raise ValueError(f"Unknown managed model: {model_id}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("model_id")
    parser.add_argument("root", type=Path)
    arguments = parser.parse_args()
    install(arguments.model_id, arguments.root)


if __name__ == "__main__":
    main()
