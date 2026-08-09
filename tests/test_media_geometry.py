import shutil
import subprocess
from pathlib import Path

import pytest

from accessible_caption_studio.exports import export_captioned_mp4
from accessible_caption_studio.media import displayed_video_dimensions, inspect_media
from accessible_caption_studio.models import CaptionCue
from accessible_caption_studio.storage import ProjectStore


def test_displayed_dimensions_apply_sample_aspect_ratio() -> None:
    assert displayed_video_dimensions(
        {"width": 720, "height": 480, "sample_aspect_ratio": "8:9"}
    ) == (640, 480)


def test_displayed_dimensions_apply_rotation_after_aspect_ratio() -> None:
    assert displayed_video_dimensions(
        {
            "width": 720,
            "height": 480,
            "sample_aspect_ratio": "8:9",
            "side_data_list": [{"rotation": 90}],
        }
    ) == (480, 640)


def _make_video(path: Path, size: str, sar: str = "1/1") -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=navy:s={size}:d=1.2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.2",
            "-vf",
            f"setsar={sar}",
            "-shortest",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _require_drawtext() -> None:
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is not installed")
    filters = subprocess.run(
        ["ffmpeg", "-filters"], capture_output=True, text=True, check=False
    ).stdout
    if " drawtext " not in filters:
        pytest.skip("FFmpeg drawtext filter is unavailable")


def _export_dimensions(tmp_path: Path, size: str, sar: str = "1/1") -> tuple[int, int]:
    _require_drawtext()
    store = ProjectStore(tmp_path / "storage")
    project = store.create(f"Geometry {size} {sar}")
    source = store.project_dir(project.id) / "source.mp4"
    _make_video(source, size, sar)
    project.media = inspect_media(source)
    project.cues = [CaptionCue(start=0, end=1, text="Geometry regression")]
    artifact = export_captioned_mp4(project, store.project_dir(project.id))
    output = store.project_dir(project.id) / "exports" / artifact.filename
    media = inspect_media(output)
    assert media.width is not None and media.height is not None
    return media.width, media.height


def test_portrait_export_preserves_portrait_geometry(tmp_path: Path) -> None:
    assert _export_dimensions(tmp_path, "180x320") == (180, 320)


def test_non_square_pixels_export_without_stretching(tmp_path: Path) -> None:
    assert _export_dimensions(tmp_path, "320x180", "2/1") == (640, 180)
