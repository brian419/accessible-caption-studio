from __future__ import annotations

import inspect

from accessible_caption_studio import model_worker, translation_worker


def test_translation_worker_pins_safetensors_checkpoint() -> None:
    assert translation_worker.MODEL_NAME == "facebook/m2m100_418M"
    assert translation_worker.MODEL_REVISION == "ae6407352f7f86e328c0f0678d466fc4246e78b3"

    source = inspect.getsource(translation_worker.translate)
    assert "revision=MODEL_REVISION" in source
    assert "use_safetensors=True" in source


def test_model_manager_uses_same_safe_translation_checkpoint() -> None:
    source = inspect.getsource(model_worker.install)
    assert "from .translation_worker import MODEL_NAME, MODEL_REVISION" in source
    assert "revision=MODEL_REVISION" in source
    assert "use_safetensors=True" in source
