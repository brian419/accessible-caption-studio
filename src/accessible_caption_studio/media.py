from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .errors import StudioError
from .models import MediaAsset

SUPPORTED_MEDIA = {".mp4", ".mov", ".webm", ".mp3", ".wav", ".m4a"}
SUPPORTED_COOKIE_BROWSERS = {"brave", "chrome", "edge", "firefox", "safari"}


def _deno_runtime() -> str | None:
    discovered = shutil.which("deno")
    if discovered:
        return discovered
    for candidate in (
        Path("/opt/local/bin/deno"),
        Path("/opt/homebrew/bin/deno"),
        Path("/usr/local/bin/deno"),
    ):
        if candidate.is_file():
            return str(candidate)
    return None


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


def extract_audio(source: Path, destination: Path, job_context: object | None = None) -> None:
    require_tools()
    partial = destination.with_suffix(".partial.wav")
    command = [
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
        ]
    runner = getattr(job_context, "run_process", None)
    process = runner(command) if runner else subprocess.run(
        command, capture_output=True, text=True, check=False
    )
    if process.returncode:
        partial.unlink(missing_ok=True)
        raise StudioError("audio_extraction_failed", "Could not extract audio from this media.")
    partial.replace(destination)


def download_youtube(
    url: str,
    destination_dir: Path,
    job_context: object | None = None,
    *,
    cookie_browser: str | None = None,
) -> tuple[Path, str]:
    if not url.startswith(
        ("https://www.youtube.com/", "https://youtube.com/", "https://youtu.be/")
    ):
        raise StudioError("invalid_url", "Enter a complete YouTube video URL.")
    if cookie_browser not in SUPPORTED_COOKIE_BROWSERS | {None}:
        raise StudioError("invalid_cookie_browser", "Choose a supported browser session.")
    template = str(destination_dir / "source.%(ext)s")
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--no-playlist",
        "--quiet",
        "--restrict-filenames",
        "-f",
        "bv*+ba/b",
        "--merge-output-format",
        "mp4",
        "-o",
        template,
        "--print",
        "after_move:%(title)s",
    ]
    deno = _deno_runtime()
    if deno:
        command.extend(["--js-runtimes", f"deno:{deno}"])
    if cookie_browser:
        command.extend(["--cookies-from-browser", cookie_browser])
    command.append(url)
    try:
        runner = getattr(job_context, "run_process", None)
        process = runner(command) if runner else subprocess.run(
            command, capture_output=True, text=True, check=False
        )
        if process.returncode:
            output = (process.stderr or process.stdout or "download failed")[-1600:]
            normalized = output.lower().replace("’", "'")
            if "sign in to confirm you're not a bot" in normalized:
                raise StudioError(
                    "youtube_auth_required",
                    "YouTube asked for a signed-in session. Return to the YouTube import, "
                    "turn on ‘Use my browser sign-in,’ choose a browser where you are signed "
                    "into YouTube, and try again.",
                )
            if "requested format is not available" in normalized and any(
                phrase in normalized
                for phrase in (
                    "javascript runtime",
                    "challenge solver",
                    "only images are available",
                    "nsig extraction failed",
                )
            ):
                raise StudioError(
                    "youtube_runtime_missing",
                    "YouTube’s download challenge could not be solved. Restart Accessible "
                    "Caption Studio so it can install the required downloader component, then "
                    "try again.",
                )
            if cookie_browser and any(
                phrase in normalized
                for phrase in (
                    "could not copy browser cookie database",
                    "failed to decrypt",
                    "could not find",
                    "cookie database",
                )
            ):
                raise StudioError(
                    "youtube_cookie_access_failed",
                    f"Could not use the {cookie_browser.title()} sign-in. Make sure YouTube is "
                    "signed in there, close the browser if it is locking its cookie database, "
                    "and try again.",
                )
            raise StudioError("youtube_download_failed", f"YouTube download failed: {output}")
        lines = [line.strip() for line in (process.stdout or "").splitlines() if line.strip()]
        title = lines[-1] if lines else "YouTube video"
    except StudioError:
        raise
    except Exception as exc:
        raise StudioError("youtube_download_failed", f"YouTube download failed: {exc}") from exc
    candidates = [path for path in destination_dir.glob("source.*") if path.suffix != ".part"]
    if not candidates:
        raise StudioError("youtube_download_failed", "The downloaded media file was not found.")
    return max(candidates, key=lambda path: path.stat().st_size), title
