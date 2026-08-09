import shutil
import subprocess
from pathlib import Path

import pytest

from accessible_caption_studio.media import inspect_media


def _ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        pytest.skip("FFmpeg is not installed")
    return executable


def _encoders() -> str:
    return subprocess.run(
        [_ffmpeg(), "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout


def _video(
    path: Path,
    size: str,
    codec: str,
    *,
    frame_rate: int = 24,
) -> None:
    encoders = _encoders()
    if codec not in encoders:
        pytest.skip(f"FFmpeg encoder {codec} is unavailable")
    if path.suffix.lower() == ".webm":
        audio_codec = "libopus"
    elif path.suffix.lower() == ".mov":
        audio_codec = "pcm_s16le"
    else:
        audio_codec = "aac"
    if audio_codec not in encoders:
        pytest.skip(f"FFmpeg encoder {audio_codec} is unavailable")
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=navy:s={size}:r={frame_rate}",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "0.25",
            "-c:v",
            codec,
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            audio_codec,
            str(path),
        ],
        check=True,
        capture_output=True,
    )


@pytest.mark.parametrize(
    ("filename", "size", "codec", "frame_rate", "expected"),
    [
        ("landscape-24fps.mp4", "320x180", "libx264", 24, (320, 180)),
        ("portrait-30fps.mp4", "180x320", "libx264", 30, (180, 320)),
        ("low-resolution-60fps.mov", "96x54", "mpeg4", 60, (96, 54)),
        ("browser-source-25fps.webm", "160x90", "libvpx-vp9", 25, (160, 90)),
        ("4k-24fps.mp4", "3840x2160", "libx264", 24, (3840, 2160)),
    ],
)
def test_generated_video_corpus(
    tmp_path: Path,
    filename: str,
    size: str,
    codec: str,
    frame_rate: int,
    expected: tuple[int, int],
) -> None:
    path = tmp_path / filename
    _video(path, size, codec, frame_rate=frame_rate)
    media = inspect_media(path)
    assert media.has_video is True
    assert media.has_audio is True
    assert (media.width, media.height) == expected


def test_generated_audio_only_corpus(tmp_path: Path) -> None:
    path = tmp_path / "audio-only.wav"
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            "0.25",
            "-c:a",
            "pcm_s16le",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    media = inspect_media(path)
    assert media.has_video is False
    assert media.has_audio is True


def test_generated_long_filename_media(tmp_path: Path) -> None:
    path = tmp_path / (("portrait-phone-source-" * 8) + ".mp4")
    _video(path, "108x192", "libx264", frame_rate=30)
    media = inspect_media(path)
    assert media.has_video is True
    assert media.has_audio is True
    assert media.width == 108
    assert media.height == 192
