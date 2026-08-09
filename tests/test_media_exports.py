import shutil
import subprocess
from pathlib import Path

import pytest

from accessible_caption_studio.exports import export_captioned_mp4, export_text
from accessible_caption_studio.media import extract_audio, inspect_media
from accessible_caption_studio.models import CaptionCue, CaptionStyle
from accessible_caption_studio.storage import ProjectStore

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is not installed")


def make_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=navy:s=320x180:d=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
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


def test_inspection_audio_extraction_and_text_exports(tmp_path: Path) -> None:
    video = tmp_path / "sample.mp4"
    make_video(video)
    media = inspect_media(video)
    assert media.has_video and media.has_audio
    assert 1.9 < media.duration < 2.1
    audio = tmp_path / "analysis.wav"
    extract_audio(video, audio)
    assert inspect_media(audio).has_video is False

    store = ProjectStore(tmp_path / "storage")
    project = store.create("Test video")
    project.cues = [CaptionCue(start=0, end=1.5, text="Hello world")]
    for format_name in ("srt", "vtt", "html"):
        artifact = export_text(project, store.project_dir(project.id), format_name)
        assert (store.project_dir(project.id) / "exports" / artifact.filename).is_file()


def test_captioned_mp4_export(tmp_path: Path) -> None:
    filters = subprocess.run(["ffmpeg", "-filters"], capture_output=True, text=True).stdout
    if " drawtext " not in filters:
        pytest.skip("FFmpeg drawtext filter is unavailable")
    store = ProjectStore(tmp_path / "storage")
    project = store.create("Captioned sample")
    project.caption_style = CaptionStyle(font_family="DejaVu Sans", font_style="Bold")
    source = store.project_dir(project.id) / "sample.mp4"
    make_video(source)
    project.media = inspect_media(source)
    project.cues = [CaptionCue(start=0, end=1.8, text="An accessible caption")]
    progress: list[tuple[int, float]] = []
    artifact = export_captioned_mp4(
        project,
        store.project_dir(project.id),
        progress=lambda percent, elapsed: progress.append((percent, elapsed)),
    )
    output = store.project_dir(project.id) / "exports" / artifact.filename
    assert output.is_file() and inspect_media(output).has_video
    assert progress
    assert progress[-1][0] == 100
    assert all(left[0] <= right[0] for left, right in zip(progress, progress[1:], strict=False))
