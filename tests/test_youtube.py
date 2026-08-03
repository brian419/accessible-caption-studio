from pathlib import Path
from types import SimpleNamespace

import pytest

from accessible_caption_studio.errors import StudioError
from accessible_caption_studio.media import download_youtube
from accessible_caption_studio.webapp import YouTubeRequest


def test_youtube_download_uses_browser_session_only_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        commands.append(command)
        (tmp_path / "source.mp4").write_bytes(b"video")
        return SimpleNamespace(returncode=0, stdout="Test video\n", stderr="")

    monkeypatch.setattr("accessible_caption_studio.media.subprocess.run", fake_run)
    monkeypatch.setattr("accessible_caption_studio.media._deno_runtime", lambda: "/deno")
    source, title = download_youtube(
        "https://www.youtube.com/watch?v=example", tmp_path, cookie_browser="chrome"
    )
    assert source.name == "source.mp4"
    assert title == "Test video"
    assert commands[0][commands[0].index("--cookies-from-browser") + 1] == "chrome"
    assert commands[0][commands[0].index("--js-runtimes") + 1].startswith("deno:")

    commands.clear()
    download_youtube("https://youtu.be/example", tmp_path)
    assert "--cookies-from-browser" not in commands[0]


def test_youtube_bot_challenge_has_clear_retry_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "accessible_caption_studio.media.subprocess.run",
        lambda *_args, **_kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="ERROR: Sign in to confirm you’re not a bot. Use --cookies-from-browser",
        ),
    )
    with pytest.raises(StudioError) as caught:
        download_youtube("https://www.youtube.com/watch?v=example", tmp_path)
    assert caught.value.code == "youtube_auth_required"
    assert "Use my browser sign-in" in caught.value.message


def test_youtube_cookie_browser_is_validated() -> None:
    request = YouTubeRequest(url="https://youtu.be/example", cookie_browser="brave")
    assert request.transcription_quality == "accurate"
    assert YouTubeRequest(url="https://youtu.be/example", cookie_browser="safari")
    with pytest.raises(ValueError):
        YouTubeRequest(url="https://youtu.be/example", cookie_browser="unknown")
