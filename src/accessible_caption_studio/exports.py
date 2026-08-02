from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .captions import to_srt, to_transcript_html, to_vtt
from .errors import StudioError
from .media import require_tools
from .models import ExportArtifact, Project
from .segmentation import wrap_caption
from .storage import safe_filename


def export_text(project: Project, project_dir: Path, format_name: str) -> ExportArtifact:
    exports = project_dir / "exports"
    exports.mkdir(exist_ok=True)
    base = safe_filename(project.name, "Accessible captions")
    if format_name == "srt":
        content, suffix = to_srt(project.cues), ".srt"
    elif format_name == "vtt":
        content, suffix = to_vtt(project.cues), ".vtt"
    elif format_name == "html":
        content, suffix = to_transcript_html(project.name, project.cues), ".html"
    else:
        raise ValueError("unsupported text export")
    destination = exports / f"{base} - accessible captions{suffix}"
    partial = destination.with_suffix(destination.suffix + ".partial")
    partial.write_text(content, encoding="utf-8")
    partial.replace(destination)
    return ExportArtifact(
        format=format_name, filename=destination.name, size_bytes=destination.stat().st_size
    )


RenderProgress = Callable[[int, float], None]


def export_captioned_mp4(
    project: Project,
    project_dir: Path,
    progress: RenderProgress | None = None,
) -> ExportArtifact:
    require_tools()
    if not project.media or not project.media.has_video:
        raise StudioError("video_required", "A captioned MP4 export requires a video source.")
    source = project_dir / project.media.stored_name
    exports = project_dir / "exports"
    exports.mkdir(exist_ok=True)
    base = safe_filename(project.name, "Accessible video")
    subtitle = project_dir / "render-captions.srt"
    render_cues = [cue.model_copy(update={"text": wrap_caption(cue.text)}) for cue in project.cues]
    subtitle.write_text(to_srt(render_cues), encoding="utf-8")
    destination = exports / f"{base} - captioned.mp4"
    partial = exports / f".{base} - captioned.partial.mp4"
    escaped = re.sub(r"([\\':,\[\]])", r"\\\1", str(subtitle))
    process = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            f"subtitles='{escaped}':force_style='FontName=Arial,FontSize=22,Outline=2,Shadow=1,MarginV=36'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "21",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            str(partial),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    duration = max(project.media.duration, 0.001)
    last_percent = -1
    try:
        if process.stdout is None:
            raise StudioError("render_failed", "FFmpeg progress output is unavailable.")
        for line in process.stdout:
            key, _, value = line.strip().partition("=")
            if key not in {"out_time_us", "out_time_ms"}:
                continue
            try:
                elapsed = int(value) / 1_000_000
            except ValueError:
                continue
            percent = min(99, max(0, round((elapsed / duration) * 100)))
            if progress and percent != last_percent:
                progress(percent, elapsed)
                last_percent = percent
        return_code = process.wait()
    except BaseException:
        process.terminate()
        process.wait()
        partial.unlink(missing_ok=True)
        raise
    finally:
        subtitle.unlink(missing_ok=True)
    if return_code:
        partial.unlink(missing_ok=True)
        details = process.stderr.read()[-500:] if process.stderr else ""
        raise StudioError("render_failed", f"Caption rendering failed: {details}")
    if progress:
        progress(100, duration)
    partial.replace(destination)
    return ExportArtifact(
        format="mp4", filename=destination.name, size_bytes=destination.stat().st_size
    )
