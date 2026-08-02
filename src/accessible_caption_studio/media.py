from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .errors import StudioError
from .models import MediaAsset

SUPPORTED_MEDIA = {".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a"}


def require_tools() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        raise StudioError("missing_ffmpeg", "FFmpeg and FFprobe are required to process media.")


def inspect_media(path: Path, *, source_url: str | None = None) -> MediaAsset:
    require_tools()
    if path.suffix.lower() not in SUPPORTED_MEDIA:
        raise StudioError(
            "unsupported_media", f"Unsupported media type: {path.suffix or 'unknown'}"
        )
    process = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode:
        raise StudioError("invalid_media", "FFprobe could not read this media file.")
    payload = json.loads(process.stdout)
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not audio:
        raise StudioError("missing_audio", "The selected media does not contain an audio track.")
    duration = float(payload.get("format", {}).get("duration") or audio.get("duration") or 0)
    if duration <= 0:
        raise StudioError("invalid_duration", "The media duration could not be determined.")
    return MediaAsset(
        filename=path.name,
        stored_name=path.name,
        content_type=None,
        duration=duration,
        width=int(video["width"]) if video and video.get("width") else None,
        height=int(video["height"]) if video and video.get("height") else None,
        has_video=video is not None,
        has_audio=True,
        source_url=source_url,
        size_bytes=path.stat().st_size,
    )


def extract_audio(source: Path, destination: Path) -> None:
    require_tools()
    partial = destination.with_suffix(".partial.wav")
    process = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(partial),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode:
        partial.unlink(missing_ok=True)
        raise StudioError("audio_extraction_failed", "Could not extract audio from this media.")
    partial.replace(destination)


def download_youtube(url: str, destination_dir: Path) -> tuple[Path, str]:
    if not url.startswith(
        ("https://www.youtube.com/", "https://youtube.com/", "https://youtu.be/")
    ):
        raise StudioError("invalid_url", "Enter a complete YouTube video URL.")
    try:
        import yt_dlp
    except ImportError as exc:
        raise StudioError("missing_downloader", "yt-dlp is not installed.") from exc
    template = str(destination_dir / "source.%(ext)s")
    options = {
        "outtmpl": template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "restrictfilenames": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            title = str(info.get("title") or "YouTube video")
    except Exception as exc:
        raise StudioError("youtube_download_failed", f"YouTube download failed: {exc}") from exc
    candidates = [path for path in destination_dir.glob("source.*") if path.suffix != ".part"]
    if not candidates:
        raise StudioError("youtube_download_failed", "The downloaded media file was not found.")
    return max(candidates, key=lambda path: path.stat().st_size), title
