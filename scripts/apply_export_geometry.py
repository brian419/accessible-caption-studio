from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "src/accessible_caption_studio/exports.py"


def replace_once(text: str, old: str, new: str) -> str:
    if old not in text:
        raise RuntimeError(f"Export patch anchor not found: {old[:60]!r}")
    return text.replace(old, new, 1)


def main() -> None:
    text = EXPORTS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .media import require_tools",
        "from .media import inspect_media, require_tools",
    )
    text = replace_once(
        text,
        '''    items = _render_items(project)\n    script = temporary_dir / "caption-filter.txt"\n    if not items:\n        script.write_text("[0:v]null[captioned]", encoding="utf-8")\n        return script\n\n    video_width = project.media.width if project.media and project.media.width else 1280\n    video_height = project.media.height if project.media and project.media.height else 720\n    entries: list[tuple[Path, float, float, int, int]] = []''',
        '''    items = _render_items(project)\n    script = temporary_dir / "caption-filter.txt"\n    video_width = project.media.width if project.media and project.media.width else 1280\n    video_height = project.media.height if project.media and project.media.height else 720\n    video_width = max(2, round(video_width / 2) * 2)\n    video_height = max(2, round(video_height / 2) * 2)\n    normalization = (\n        f"scale={video_width}:{video_height}:flags=lanczos,setsar=1"\n    )\n    if not items:\n        script.write_text(\n            f"[0:v]{normalization}[captioned]", encoding="utf-8"\n        )\n        return script\n\n    entries: list[tuple[Path, float, float, int, int]] = []''',
    )
    text = replace_once(
        text,
        '''    current = "[0:v]"\n    filters: list[str] = []''',
        '''    current = "[normalized]"\n    filters: list[str] = [f"[0:v]{normalization}[normalized]"]''',
    )
    text = replace_once(
        text,
        '''        with tempfile.TemporaryDirectory(prefix=".caption-render-", dir=project_dir) as temp_name:\n            script = _write_filter_script(project, Path(temp_name))''',
        '''        with tempfile.TemporaryDirectory(\n            prefix=".caption-render-", dir=project_dir\n        ) as temp_name:\n            render_media = inspect_media(source)\n            render_project = project.model_copy(deep=True)\n            if render_project.media:\n                render_project.media.width = render_media.width\n                render_project.media.height = render_media.height\n            script = _write_filter_script(render_project, Path(temp_name))''',
    )
    text = replace_once(
        text,
        '''                    "-crf",\n                    "21",\n                    "-c:a",''',
        '''                    "-crf",\n                    "21",\n                    "-pix_fmt",\n                    "yuv420p",\n                    "-metadata:s:v:0",\n                    "rotate=0",\n                    "-c:a",''',
    )
    EXPORTS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
