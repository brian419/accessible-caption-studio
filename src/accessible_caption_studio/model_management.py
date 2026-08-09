from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from .models import utc_now

MODEL_SPECS = (
    ("whisper-en-fast", "Whisper English - Fast", "Small English transcription model"),
    ("whisper-en-accurate", "Whisper English - Accurate", "Distil-Whisper Large v3 transcription model"),
    ("whisper-multilingual-fast", "Whisper Multilingual - Fast", "Small multilingual Whisper model"),
    ("whisper-multilingual-accurate", "Whisper Multilingual - Accurate", "Large v3 multilingual Whisper model"),
    ("speaker-ecapa", "ECAPA speaker labeling", "Anonymous local voice embeddings"),
    ("speaker-wavlm", "WavLM voice matching", "Supporting voice matching for overlap analysis"),
    ("sound-ast", "AST sound recognition", "Meaningful non-speech sound detection"),
    ("overlap-sepformer", "SepFormer overlap separation", "Two-speaker separation for selected intervals"),
    ("face-yunet-sface", "YuNet + SFace", "Anonymous local face detection and matching"),
    ("translation-m2m100", "M2M100 translation", "Local many-to-many caption translation model"),
)


class ModelManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.marker_dir = self.root / ".managed"
        self.marker_dir.mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self._status: dict[str, str] = {}
        self._errors: dict[str, str] = {}

    @staticmethod
    def ids() -> set[str]:
        return {item[0] for item in MODEL_SPECS}

    def list(self) -> list[dict[str, object]]:
        rows = []
        with self._lock:
            for model_id, label, description in MODEL_SPECS:
                paths = self._paths(model_id)
                installed = bool(paths) or self._marker(model_id).is_file()
                rows.append(
                    {
                        "id": model_id,
                        "label": label,
                        "description": description,
                        "installed": installed,
                        "size_bytes": self._size(paths),
                        "status": self._status.get(
                            model_id, "installed" if installed else "not_installed"
                        ),
                        "error": self._errors.get(model_id),
                    }
                )
        return rows

    def install(self, model_id: str) -> dict[str, object]:
        self._require(model_id)
        with self._lock:
            if self._status.get(model_id) == "installing":
                return self._record(model_id)
            self._status[model_id] = "installing"
            self._errors.pop(model_id, None)
        threading.Thread(target=self._run_install, args=(model_id,), daemon=True).start()
        return self._record(model_id)

    def remove(self, model_id: str) -> dict[str, object]:
        self._require(model_id)
        with self._lock:
            if self._status.get(model_id) == "installing":
                raise ValueError("Wait for the model download to finish before removing it")
            for path in self._paths(model_id):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            self._marker(model_id).unlink(missing_ok=True)
            self._status[model_id] = "not_installed"
            self._errors.pop(model_id, None)
        return self._record(model_id)

    def _run_install(self, model_id: str) -> None:
        command = [
            sys.executable,
            "-m",
            "accessible_caption_studio.model_worker",
            model_id,
            str(self.root),
        ]
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        with self._lock:
            if process.returncode:
                detail = (process.stderr or process.stdout or "Model download failed").strip()
                self._status[model_id] = "error"
                self._errors[model_id] = detail[-900:]
            else:
                self._status[model_id] = "installed"
                self._errors.pop(model_id, None)
                self._marker(model_id).write_text(
                    json.dumps({"installed_at": utc_now().isoformat()}), encoding="utf-8"
                )

    def _record(self, model_id: str) -> dict[str, object]:
        return next(item for item in self.list() if item["id"] == model_id)

    def _require(self, model_id: str) -> None:
        if model_id not in self.ids():
            raise KeyError(model_id)

    def _marker(self, model_id: str) -> Path:
        return self.marker_dir / f"{model_id}.json"

    @staticmethod
    def _size(paths: list[Path]) -> int:
        files: set[Path] = set()
        total = 0
        for path in paths:
            if path.is_file():
                files.add(path)
            elif path.is_dir():
                files.update(item for item in path.rglob("*") if item.is_file())
        for path in files:
            try:
                total += path.stat().st_size
            except OSError:
                pass
        return total

    def _paths(self, model_id: str) -> list[Path]:
        exact = {
            "speaker-ecapa": [self.root / "ecapa-voxceleb"],
            "speaker-wavlm": [self.root / "huggingface" / "models--microsoft--wavlm-base-plus-sv"],
            "sound-ast": [self.root / "huggingface" / "models--MIT--ast-finetuned-audioset-10-10-0.4593"],
            "overlap-sepformer": [self.root / "speechbrain" / "sepformer-whamr16k"],
            "face-yunet-sface": [self.root / "opencv-face"],
            "translation-m2m100": [
                self.root / "huggingface" / "models--facebook--m2m100_418M"
            ],
        }
        if model_id in exact:
            return [path for path in exact[model_id] if path.exists()]
        whisper = self.root / "whisper"
        if not whisper.is_dir():
            return []
        matches: list[Path] = []
        for path in whisper.iterdir():
            name = path.name.casefold().replace("_", "-")
            is_distil = "distil" in name and "large-v3" in name
            is_large = "large-v3" in name and not is_distil
            is_small_en = "small.en" in name or "small-en" in name
            is_small = "small" in name and not is_small_en
            wanted = {
                "whisper-en-fast": is_small_en,
                "whisper-en-accurate": is_distil,
                "whisper-multilingual-fast": is_small,
                "whisper-multilingual-accurate": is_large,
            }.get(model_id, False)
            if wanted:
                matches.append(path)
        return matches
