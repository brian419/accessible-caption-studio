from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from .captions import to_srt, to_transcript_html, to_vtt
from .errors import StudioError
from .media import inspect_media, require_tools
from .models import CaptionCue, CaptionStyle, ExportArtifact, Project
from .storage import safe_filename

try:
    from PIL import ImageFont
except ImportError:  # Pillow is optional; a conservative width estimate remains available.
    ImageFont = None


def export_text(project: Project, project_dir: Path, format_name: str) -> ExportArtifact:
    exports = project_dir / "exports"
    exports.mkdir(exist_ok=True)
    base = safe_filename(project.name, "Accessible captions")
    display_cues = [
        cue.model_copy(update={"speaker": project.speaker_names.get(cue.speaker, cue.speaker)})
        for cue in project.cues
    ]
    if format_name == "srt":
        content, suffix = to_srt(display_cues), ".srt"
    elif format_name == "vtt":
        content, suffix = to_vtt(display_cues), ".vtt"
    elif format_name == "html":
        content, suffix = to_transcript_html(project.name, display_cues), ".html"
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


def _caption_text(project: Project, cue: CaptionCue) -> str:
    speaker = project.speaker_names.get(cue.speaker, cue.speaker)
    return f"{speaker}: {cue.text}" if speaker else cue.text


def _render_items(project: Project) -> list[tuple[float, float, str]]:
    """Match the browser preview by joining intentionally grouped overlapping cues."""
    ordered = sorted(project.cues, key=lambda cue: (cue.start, cue.end, cue.id))
    grouped: dict[str, list[CaptionCue]] = {}
    for cue in ordered:
        if cue.overlap_group_id:
            grouped.setdefault(cue.overlap_group_id, []).append(cue)

    rendered: list[tuple[float, float, str]] = []
    seen_groups: set[str] = set()
    for cue in ordered:
        group_id = cue.overlap_group_id
        if group_id:
            if group_id in seen_groups:
                continue
            seen_groups.add(group_id)
            members = grouped[group_id]
            rendered.append(
                (
                    min(member.start for member in members),
                    max(member.end for member in members),
                    "\n".join(_caption_text(project, member) for member in members),
                )
            )
        else:
            rendered.append((cue.start, cue.end, _caption_text(project, cue)))
    return rendered


def _escape_filter_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")


def _ffmpeg_color(value: str) -> str:
    return f"0x{value.lstrip('#')}"


def _font_pattern(style: CaptionStyle) -> str:
    font_style = style.font_style or ("Bold" if style.bold else "Regular")
    return f"{style.font_family}:style={font_style}"


@lru_cache(maxsize=128)
def _font_match(font_pattern: str) -> tuple[Path | None, tuple[str, ...], tuple[str, ...]]:
    try:
        match = subprocess.run(
            ["fc-match", "-f", "%{family}\t%{style}\t%{file}", font_pattern],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        family_value, separator, remainder = match.stdout.strip().partition("\t")
        style_value, style_separator, file_value = remainder.partition("\t")
        if match.returncode != 0 or not separator or not style_separator:
            return None, (), ()
        font_path = Path(file_value) if file_value and Path(file_value).is_file() else None
        families = tuple(item.strip() for item in family_value.split(",") if item.strip())
        styles = tuple(item.strip() for item in style_value.split(",") if item.strip())
        return font_path, families, styles
    except (OSError, subprocess.SubprocessError):
        return None, (), ()


def _require_caption_font(style: CaptionStyle) -> None:
    if not shutil.which("fc-match"):
        return
    font_path, families, styles = _font_match(_font_pattern(style))
    requested_family = style.font_family.casefold()
    requested_style = (style.font_style or ("Bold" if style.bold else "Regular")).casefold()
    available_families = {family.casefold() for family in families}
    available_styles = {font_style.casefold() for font_style in styles}
    if not font_path or requested_family not in available_families:
        raise StudioError(
            "caption_font_unavailable",
            f'The caption font "{style.font_family}" is no longer installed. '
            "Choose another font in Customize captions before exporting.",
        )
    if requested_style not in available_styles:
        raise StudioError(
            "caption_font_style_unavailable",
            f'The "{style.font_style}" style for "{style.font_family}" is no longer installed. '
            "Choose another font style before exporting.",
        )


@lru_cache(maxsize=64)
def _caption_font(font_pattern: str, font_size: int):
    if ImageFont is None:
        return None
    font_path, _families, _styles = _font_match(font_pattern)
    if font_path:
        try:
            return ImageFont.truetype(font_path, font_size)
        except (OSError, ValueError):
            pass
    return None


def _estimated_text_width(text: str, style: CaptionStyle, font_size: int) -> float:
    if not text:
        return 0.0
    family_adjustment = {
        "Arial": 0.0,
        "Helvetica": 0.0,
        "Verdana": 0.04,
        "Georgia": 0.02,
        "Courier New": 0.06,
    }.get(style.font_family, 0.0)
    normalized_style = (style.font_style or "").casefold()
    bold_adjustment = 0.025 if style.bold else 0.0
    italic_adjustment = 0.012 if any(marker in normalized_style for marker in ("italic", "oblique")) else 0.0
    total = 0.0
    for character in text:
        if character.isspace():
            factor = 0.34
        elif character in "ilI.,'`:;!|[](){}":
            factor = 0.31
        elif character in "MW@%&QO0#":
            factor = 0.9
        elif character.isupper():
            factor = 0.7
        elif character.isdigit():
            factor = 0.61
        elif ord(character) > 127:
            factor = 0.95
        else:
            factor = 0.57
        total += factor + family_adjustment + bold_adjustment + italic_adjustment
    return total * font_size * 1.05


def _text_width(text: str, style: CaptionStyle, font_size: int) -> float:
    font = _caption_font(_font_pattern(style), font_size)
    if font is not None:
        try:
            return float(font.getlength(text))
        except (AttributeError, OSError, ValueError):
            pass
    return _estimated_text_width(text, style, font_size)


def _split_wide_word(
    word: str, style: CaptionStyle, font_size: int, maximum_width: float
) -> list[str]:
    pieces: list[str] = []
    piece = ""
    for character in word:
        candidate = piece + character
        if piece and _text_width(candidate, style, font_size) > maximum_width:
            pieces.append(piece)
            piece = character
        else:
            piece = candidate
    if piece:
        pieces.append(piece)
    return pieces


def _wrap_export_text(
    text: str, style: CaptionStyle, video_width: int, video_height: int
) -> list[str]:
    font_size = max(12, round(video_height * style.font_size_percent / 100))
    padding = max(1, round(video_height * style.padding_percent / 100))
    outline = max(0, round(video_height * style.outline_size_percent / 100))
    shadow = max(0, round(video_height * style.shadow_size_percent / 100))
    maximum_box_width = max(1.0, video_width * style.max_width_percent / 100)
    maximum_text_width = max(
        1.0, maximum_box_width - (padding * 2) - (outline * 2) - shadow
    )
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        words = paragraph.strip().split()
        if not words:
            continue
        line = ""
        for word in words:
            pieces = (
                _split_wide_word(word, style, font_size, maximum_text_width)
                if _text_width(word, style, font_size) > maximum_text_width
                else [word]
            )
            for piece in pieces:
                candidate = f"{line} {piece}" if line else piece
                if line and _text_width(candidate, style, font_size) > maximum_text_width:
                    lines.append(line)
                    line = piece
                else:
                    line = candidate
        if line:
            lines.append(line)
    return lines or [""]


def _drawtext_filter(
    style: CaptionStyle,
    text_path: Path,
    start: float,
    end: float,
    video_height: int,
    line_index: int,
    total_lines: int,
) -> str:
    font_size = max(12, round(video_height * style.font_size_percent / 100))
    padding = max(1, round(video_height * style.padding_percent / 100))
    outline = max(0, round(video_height * style.outline_size_percent / 100))
    shadow = max(0, round(video_height * style.shadow_size_percent / 100))
    line_spacing = max(0, round(video_height * style.line_spacing_percent / 100))
    margin = style.vertical_margin_percent / 100
    line_step = font_size + (padding * 2) + line_spacing
    total_height = (font_size + (padding * 2)) * total_lines + line_spacing * (total_lines - 1)
    line_offset = line_index * line_step

    if style.alignment == "left":
        x = "w*0.06"
    elif style.alignment == "right":
        x = "w-text_w-w*0.06"
    else:
        x = "(w-text_w)/2"

    if style.position == "top":
        y = f"h*{margin:.4f}+{line_offset}"
    elif style.position == "middle":
        y = f"(h-{total_height})/2+{line_offset}"
    else:
        y = f"h-h*{margin:.4f}-{total_height}+{line_offset}"

    font_pattern = _font_pattern(style)
    font_path, _families, _styles = _font_match(font_pattern)
    font_option = (
        f"fontfile='{_escape_filter_value(str(font_path))}'"
        if font_path
        else f"font='{_escape_filter_value(style.font_family)}'"
    )

    options = [
        font_option,
        f"textfile='{_escape_filter_value(str(text_path))}'",
        "expansion=none",
        f"fontcolor={_ffmpeg_color(style.text_color)}",
        f"fontsize={font_size}",
        f"line_spacing={line_spacing}",
        f"borderw={outline}",
        f"bordercolor={_ffmpeg_color(style.outline_color)}",
        f"shadowx={shadow}",
        f"shadowy={shadow}",
        f"shadowcolor={_ffmpeg_color(style.shadow_color)}@0.85",
        f"box={1 if style.background_opacity > 0 else 0}",
        f"boxcolor={_ffmpeg_color(style.background_color)}@{style.background_opacity:.3f}",
        f"boxborderw={padding}",
        "fix_bounds=true",
        f"x={x}",
        f"y={y}",
        f"enable='between(t,{max(0.0, start):.3f},{max(start, end):.3f})'",
    ]
    return "drawtext=" + ":".join(options)


def _write_filter_script(project: Project, temporary_dir: Path) -> Path:
    items = _render_items(project)
    script = temporary_dir / "caption-filter.txt"
    video_width = project.media.width if project.media and project.media.width else 1280
    video_height = project.media.height if project.media and project.media.height else 720
    video_width = max(2, round(video_width / 2) * 2)
    video_height = max(2, round(video_height / 2) * 2)
    normalization = (
        f"scale={video_width}:{video_height}:flags=lanczos,setsar=1"
    )
    if not items:
        script.write_text(
            f"[0:v]{normalization}[captioned]", encoding="utf-8"
        )
        return script

    entries: list[tuple[Path, float, float, int, int]] = []
    for item_index, (start, end, text) in enumerate(items):
        lines = _wrap_export_text(text, project.caption_style, video_width, video_height)
        for line_index, line in enumerate(lines):
            text_path = temporary_dir / f"caption-{item_index:05d}-{line_index:02d}.txt"
            text_path.write_text(line, encoding="utf-8")
            entries.append((text_path, start, end, line_index, len(lines)))

    current = "[normalized]"
    filters: list[str] = [f"[0:v]{normalization}[normalized]"]
    for index, (text_path, start, end, line_index, total_lines) in enumerate(entries):
        output = "[captioned]" if index == len(entries) - 1 else f"[caption{index}]"
        drawtext = _drawtext_filter(
            project.caption_style,
            text_path,
            start,
            end,
            video_height,
            line_index,
            total_lines,
        )
        filters.append(f"{current}{drawtext}{output}")
        current = output
    script.write_text(";\n".join(filters), encoding="utf-8")
    return script


def export_captioned_mp4(
    project: Project,
    project_dir: Path,
    progress: RenderProgress | None = None,
    job_context: object | None = None,
) -> ExportArtifact:
    require_tools()
    if not project.media or not project.media.has_video:
        raise StudioError("video_required", "A captioned MP4 export requires a video source.")
    _require_caption_font(project.caption_style)
    source = project_dir / project.media.stored_name
    exports = project_dir / "exports"
    exports.mkdir(exist_ok=True)
    base = safe_filename(project.name, "Accessible video")
    destination = exports / f"{base} - captioned.mp4"
    partial = exports / f".{base} - captioned.partial.mp4"
    partial.unlink(missing_ok=True)

    register = getattr(job_context, "register_process", None)
    unregister = getattr(job_context, "unregister_process", None)
    duration = max(project.media.duration, 0.001)
    last_percent = -1
    process: subprocess.Popen[str] | None = None

    try:
        with tempfile.TemporaryDirectory(
            prefix=".caption-render-", dir=project_dir
        ) as temp_name:
            render_media = inspect_media(source)
            render_project = project.model_copy(deep=True)
            if render_project.media:
                render_project.media.width = render_media.width
                render_project.media.height = render_media.height
            script = _write_filter_script(render_project, Path(temp_name))
            process = subprocess.Popen(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-filter_complex_script",
                    str(script),
                    "-map",
                    "[captioned]",
                    "-map",
                    "0:a?",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "21",
                    "-pix_fmt",
                    "yuv420p",
                    "-metadata:s:v:0",
                    "rotate=0",
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
                start_new_session=True,
            )
            if register:
                register(process)
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
                if process.poll() is None:
                    process.terminate()
                    process.wait()
                partial.unlink(missing_ok=True)
                raise
            finally:
                if unregister:
                    unregister(process)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise

    if return_code:
        partial.unlink(missing_ok=True)
        details = process.stderr.read()[-500:] if process and process.stderr else ""
        raise StudioError("render_failed", f"Caption rendering failed: {details}")
    if progress:
        progress(100, duration)
    partial.replace(destination)
    return ExportArtifact(
        format="mp4", filename=destination.name, size_bytes=destination.stat().st_size
    )
