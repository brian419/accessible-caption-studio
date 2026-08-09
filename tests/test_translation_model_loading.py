from __future__ import annotations

import inspect
from pathlib import Path

from accessible_caption_studio import model_worker, translation_worker

ROOT = Path(__file__).resolve().parents[1]


def test_translation_worker_pins_safetensors_checkpoint() -> None:
    assert translation_worker.MODEL_NAME == "facebook/m2m100_418M"
    assert translation_worker.MODEL_REVISION == "ae6407352f7f86e328c0f0678d466fc4246e78b3"

    source = inspect.getsource(translation_worker.translate)
    assert "revision=MODEL_REVISION" in source
    assert "use_safetensors=True" in source
    assert "low_cpu_mem_usage=False" in source
    assert 'model.to("cpu")' not in source
    assert 'parameter.device.type == "meta"' in source


def test_model_manager_uses_same_safe_translation_checkpoint() -> None:
    source = inspect.getsource(model_worker.install)
    assert "from .translation_worker import MODEL_NAME, MODEL_REVISION" in source
    assert "revision=MODEL_REVISION" in source
    assert "use_safetensors=True" in source
    assert "low_cpu_mem_usage=False" in source


def test_ml_dependencies_pin_pre_meta_loader_transformers() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"transformers>=4.48,<4.51"' in pyproject


def test_launchers_refresh_the_managed_environment_for_translation_fix() -> None:
    launcher_paths = (
        ROOT / "Start Accessible Caption Studio.command",
        ROOT / "start-accessible-caption-studio.sh",
        ROOT / "Start Accessible Caption Studio.ps1",
    )
    for path in launcher_paths:
        source = path.read_text(encoding="utf-8")
        assert ".setup-complete-v6" in source
