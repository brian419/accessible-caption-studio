from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

MODEL_NAME = "facebook/m2m100_418M"
MODEL_REVISION = "ae6407352f7f86e328c0f0678d466fc4246e78b3"


def translate(
    source_language: str,
    target_language: str,
    input_path: Path,
    output_path: Path,
    model_dir: Path,
) -> None:
    import torch
    from transformers import M2M100ForConditionalGeneration, M2M100Tokenizer

    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    cache_dir = model_dir / "huggingface"
    cache_dir.mkdir(parents=True, exist_ok=True)
    tokenizer = M2M100Tokenizer.from_pretrained(
        MODEL_NAME,
        revision=MODEL_REVISION,
        cache_dir=str(cache_dir),
    )
    model = M2M100ForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        revision=MODEL_REVISION,
        cache_dir=str(cache_dir),
        use_safetensors=True,
    )
    model.to("cpu")
    model.eval()
    tokenizer.src_lang = source_language

    texts = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(texts, list) or not all(isinstance(item, str) for item in texts):
        raise ValueError("Translation input must be a list of caption strings")

    translated: list[str] = []
    forced_bos_token_id = tokenizer.get_lang_id(target_language)
    with torch.inference_mode():
        for start in range(0, len(texts), 8):
            batch = texts[start : start + 8]
            encoded = tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=256,
            )
            generated = model.generate(
                **encoded,
                forced_bos_token_id=forced_bos_token_id,
                max_length=256,
                num_beams=4,
                early_stopping=True,
            )
            translated.extend(
                tokenizer.batch_decode(generated, skip_special_tokens=True)
            )

    temporary = output_path.with_suffix(".partial.json")
    temporary.write_text(json.dumps(translated, ensure_ascii=False), encoding="utf-8")
    temporary.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_language")
    parser.add_argument("target_language")
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("model_dir", type=Path)
    arguments = parser.parse_args()
    translate(
        arguments.source_language,
        arguments.target_language,
        arguments.input_path,
        arguments.output_path,
        arguments.model_dir,
    )


if __name__ == "__main__":
    main()
