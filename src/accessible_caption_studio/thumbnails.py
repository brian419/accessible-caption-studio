from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .errors import StudioError
from .models import Project


def ensure_project_thumbnail(project: Project, project_dir: Path) -> Path | None:
    if not project.media or not project.media.has_video:
        return None
    destination = project_dir / "thumbnail.jpg"
    if destination.is_file() and destination.stat().st_size:
        return destination
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StudioError("ffmpeg_missing", "FFmpeg is required to create project thumbnails.")
    source = project_dir / project.media.stored_name
    if not source.is_file():
        return None
    duration = max(0.0, float(project.media.duration or 0))
    seek = min(max(duration * 0.2, 0.0), max(0.0, duration - 0.05))
    partial = project_dir / "thumbnail.partial.jpg"
    command = [
        ffmpeg,
        "-y",
        "-ss",
        f"{seek:.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        "scale=320:-2:force_original_aspect_ratio=decrease",
        "-q:v",
        "4",
        str(partial),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode or not partial.is_file():
        partial.unlink(missing_ok=True)
        raise StudioError(
            "thumbnail_failed",
            "A local preview thumbnail could not be created for this video.",
        )
    partial.replace(destination)
    return destination
