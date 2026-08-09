from __future__ import annotations

from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, *, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, count), encoding="utf-8")


def replace_all(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected patch anchor not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dedent(content).lstrip(), encoding="utf-8")


# Project schema v3: multilingual transcription, selectable SDH behavior, persisted retry parameters.
replace(
    "src/accessible_caption_studio/models.py",
    '    result: dict[str, Any] | None = None\n    created_at: datetime = Field(default_factory=utc_now)\n',
    '    parameters: dict[str, Any] = Field(default_factory=dict)\n    result: dict[str, Any] | None = None\n    created_at: datetime = Field(default_factory=utc_now)\n',
)
replace(
    "src/accessible_caption_studio/models.py",
    '    transcription_quality: str = Field(default="accurate", pattern="^(fast|accurate)$")\n    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)\n',
    '    transcription_quality: str = Field(default="accurate", pattern="^(fast|accurate)$")\n    transcription_language: str = Field(\n        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"\n    )\n    sdh_mode: Literal["off", "conservative", "full"] = "full"\n    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)\n',
)
replace(
    "src/accessible_caption_studio/migrations.py",
    "CURRENT_PROJECT_SCHEMA_VERSION = 2",
    "CURRENT_PROJECT_SCHEMA_VERSION = 3",
)
replace(
    "src/accessible_caption_studio/migrations.py",
    '        if version == 1:\n            data.setdefault("is_favorite", False)\n            for cue in data.get("cues", []) or []:\n                if isinstance(cue, dict):\n                    cue.setdefault("position_override", None)\n                    cue.setdefault("alignment_override", None)\n                    cue.setdefault("vertical_margin_percent_override", None)\n            data["schema_version"] = 2\n            version = 2\n            changed = True\n            continue\n        raise ValueError(f"No migration path exists for project schema version {version}")\n',
    '        if version == 1:\n            data.setdefault("is_favorite", False)\n            for cue in data.get("cues", []) or []:\n                if isinstance(cue, dict):\n                    cue.setdefault("position_override", None)\n                    cue.setdefault("alignment_override", None)\n                    cue.setdefault("vertical_margin_percent_override", None)\n            data["schema_version"] = 2\n            version = 2\n            changed = True\n            continue\n        if version == 2:\n            data.setdefault("transcription_language", "en")\n            data.setdefault("sdh_mode", "full")\n            data["schema_version"] = 3\n            version = 3\n            changed = True\n            continue\n        raise ValueError(f"No migration path exists for project schema version {version}")\n',
)

# Persist job inputs so interrupted operations can be reconstructed safely.
replace(
    "src/accessible_caption_studio/jobs.py",
    "from collections.abc import Callable\n",
    "from collections.abc import Callable\nfrom typing import Any\n",
)
replace(
    "src/accessible_caption_studio/jobs.py",
    '    def start(\n        self,\n        project_id: str,\n        kind: str,\n        target: Callable[[AnalysisJob, Callable[[str, int, str], None]], None],\n    ) -> AnalysisJob:\n        job = AnalysisJob(project_id=project_id, kind=kind)\n',
    '    def start(\n        self,\n        project_id: str,\n        kind: str,\n        target: Callable[[AnalysisJob, Callable[[str, int, str], None]], None],\n        parameters: dict[str, Any] | None = None,\n    ) -> AnalysisJob:\n        job = AnalysisJob(\n            project_id=project_id, kind=kind, parameters=dict(parameters or {})\n        )\n',
)

# Multilingual Faster-Whisper worker support.
replace(
    "src/accessible_caption_studio/whisper_worker.py",
    '    model_name: str = "distil-large-v3",\n) -> None:\n',
    '    model_name: str = "distil-large-v3",\n    language: str | None = None,\n) -> None:\n',
)
replace(
    "src/accessible_caption_studio/whisper_worker.py",
    '            word_timestamps=True,\n            vad_filter=False,\n',
    '            word_timestamps=True,\n            language=language,\n            vad_filter=False,\n',
)
replace(
    "src/accessible_caption_studio/whisper_worker.py",
    '        choices=("small.en", "distil-large-v3"),\n        default="distil-large-v3",\n    )\n    parser.add_argument("--vad-only", action="store_true")\n',
    '        choices=("small.en", "distil-large-v3", "small", "large-v3"),\n        default="distil-large-v3",\n    )\n    parser.add_argument("--language")\n    parser.add_argument("--vad-only", action="store_true")\n',
)
replace(
    "src/accessible_caption_studio/whisper_worker.py",
    '            arguments.intervals,\n            arguments.model,\n        )\n',
    '            arguments.intervals,\n            arguments.model,\n            arguments.language,\n        )\n',
)

write(
    "src/accessible_caption_studio/enhanced_analyzer.py",
    r'''
    from __future__ import annotations

    import json
    import subprocess
    import sys
    import tempfile
    import wave
    from pathlib import Path

    from .analyzer import LocalAnalyzer as BaseLocalAnalyzer
    from .analyzer import ProgressCallback
    from .errors import SetupError, StudioError
    from .models import CaptionCue, SoundEvent, WordToken
    from .transcription import detect_recovery_regions, merge_recovery_words


    class LocalAnalyzer(BaseLocalAnalyzer):
        """Current analyzer plus multilingual Whisper and selectable SDH behavior."""

        def __init__(
            self,
            model_dir: Path,
            transcription_quality: str = "accurate",
            transcription_language: str = "en",
            sdh_mode: str = "full",
        ) -> None:
            super().__init__(model_dir, transcription_quality)
            language = str(transcription_language or "en").strip()
            self.transcription_language = language if language else "en"
            self.sdh_mode = sdh_mode if sdh_mode in {"off", "conservative", "full"} else "full"

        def _language_code(self) -> str | None:
            if self.transcription_language == "auto":
                return None
            return self.transcription_language.split("-", 1)[0].lower()

        def _uses_english_model(self) -> bool:
            return self._language_code() == "en"

        def _whisper_model_name(self) -> str:
            if self._uses_english_model():
                return "small.en" if self.transcription_quality == "fast" else "distil-large-v3"
            return "small" if self.transcription_quality == "fast" else "large-v3"

        def _whisper_command(
            self,
            audio_path: Path,
            output_path: Path,
            intervals_path: Path | None = None,
        ) -> list[str]:
            whisper_dir = self.model_dir / "whisper"
            whisper_dir.mkdir(parents=True, exist_ok=True)
            command = [
                sys.executable,
                "-m",
                "accessible_caption_studio.whisper_worker",
                "--model",
                self._whisper_model_name(),
            ]
            language = self._language_code()
            if language:
                command.extend(["--language", language])
            command.extend([str(audio_path), str(whisper_dir), str(output_path)])
            if intervals_path:
                command.extend(["--intervals", str(intervals_path)])
            return command

        def _run_whisper(
            self,
            audio_path: Path,
            output_path: Path,
            intervals_path: Path | None = None,
            progress: ProgressCallback | None = None,
        ) -> subprocess.CompletedProcess[str]:
            command = self._whisper_command(audio_path, output_path, intervals_path)
            reporter = progress or getattr(self, "_progress", None)
            runner = getattr(reporter, "run_process", None)
            return (
                runner(command)
                if runner
                else subprocess.run(command, capture_output=True, text=True, check=False)
            )

        def transcribe(self, audio_path: Path) -> list[WordToken]:
            if self._uses_english_model():
                return super().transcribe(audio_path)
            with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
                output_path = Path(temporary_dir) / "words.json"
                process = self._run_whisper(audio_path, output_path)
                if process.returncode:
                    details = (process.stderr or process.stdout or "").strip()
                    if "No module named 'faster_whisper'" in details:
                        raise SetupError(
                            "ml_not_installed",
                            "Automatic transcription is not installed. Run setup from the launcher.",
                        )
                    raise StudioError(
                        "transcription_failed",
                        f"Whisper transcription failed: {details[-1000:]}",
                    )
                try:
                    return [
                        WordToken.model_validate(item)
                        for item in json.loads(output_path.read_text(encoding="utf-8"))
                    ]
                except (OSError, ValueError) as exc:
                    raise StudioError(
                        "transcription_failed", "Whisper returned an unreadable result."
                    ) from exc

        def recover_transcription(
            self,
            audio_path: Path,
            words: list[WordToken],
            progress: ProgressCallback | None = None,
            camera_cuts: list[float] | None = None,
        ) -> tuple[list[WordToken], dict[str, object]]:
            if self._uses_english_model():
                return super().recover_transcription(audio_path, words, progress, camera_cuts)

            speech_regions = self.detect_speech_regions(audio_path, progress)
            try:
                regions = detect_recovery_regions(
                    audio_path,
                    words,
                    camera_cuts,
                    speech_regions=speech_regions,
                )
            except (OSError, EOFError, wave.Error):
                regions = []
            empty: dict[str, object] = {
                "inserted": 0,
                "replaced": 0,
                "discarded": 0,
                "regions": regions,
            }
            if not regions:
                return words, empty
            if progress:
                progress(
                    "Recovering missed dialogue",
                    45,
                    f"Rechecking {len(regions)} suspicious speech region"
                    f"{'s' if len(regions) != 1 else ''}",
                )
            with tempfile.TemporaryDirectory(dir=self.model_dir) as temporary_dir:
                output_path = Path(temporary_dir) / "recovered-words.json"
                intervals_path = Path(temporary_dir) / "recovery-intervals.json"
                intervals_path.write_text(
                    json.dumps(
                        [{"start": start, "end": end} for start, end in regions]
                    ),
                    encoding="utf-8",
                )
                process = self._run_whisper(
                    audio_path, output_path, intervals_path, progress
                )
                if process.returncode:
                    detail = (process.stderr or process.stdout or "").strip()
                    raise StudioError(
                        "transcript_recovery_failed",
                        "The primary transcript was kept because local dialogue recovery "
                        f"could not finish: {detail[-700:]}",
                    )
                try:
                    recovered = [
                        WordToken.model_validate(item)
                        for item in json.loads(output_path.read_text(encoding="utf-8"))
                    ]
                except (OSError, ValueError) as exc:
                    raise StudioError(
                        "transcript_recovery_failed",
                        "The primary transcript was kept because recovery returned unreadable data.",
                    ) from exc
            merged, summary = merge_recovery_words(words, recovered)
            return merged, {**summary, "regions": regions}

        def detect_sounds(self, audio_path: Path) -> list[SoundEvent]:
            if self.sdh_mode == "off":
                return []
            events = super().detect_sounds(audio_path)
            if self.sdh_mode == "conservative":
                return [event for event in events if event.confidence >= 0.60]
            return events

        def sound_cues(
            self, events: list[SoundEvent], speech: list[CaptionCue]
        ) -> list[CaptionCue]:
            if self.sdh_mode == "off":
                return []
            if self.sdh_mode == "conservative":
                events = [event for event in events if event.confidence >= 0.60]
            return BaseLocalAnalyzer.sound_cues(events, speech)
    ''',
)

# Make overlap analysis use the same language/quality choice as the parent project.
replace(
    "src/accessible_caption_studio/analyzer.py",
    '                    str(references_path),\n                    str(output_path),\n                ],\n',
    '                    str(references_path),\n                    str(output_path),\n                    str(getattr(self, "transcription_language", "en")),\n                    str(getattr(self, "transcription_quality", "accurate")),\n                ],\n',
)
replace(
    "src/accessible_caption_studio/overlap_worker.py",
    '    output_path: Path,\n) -> None:\n',
    '    output_path: Path,\n    transcription_language: str = "en",\n    transcription_quality: str = "accurate",\n) -> None:\n',
)
replace(
    "src/accessible_caption_studio/overlap_worker.py",
    '            process = subprocess.run(\n                [\n                    sys.executable,\n                    "-m",\n                    "accessible_caption_studio.whisper_worker",\n                    str(channel_path),\n                    str(whisper_dir),\n                    str(words_path),\n                ],\n                capture_output=True,\n                text=True,\n                check=False,\n            )\n',
    '            language = transcription_language.split("-", 1)[0].lower()\n            english = language == "en"\n            model_name = (\n                "small.en"\n                if english and transcription_quality == "fast"\n                else "distil-large-v3"\n                if english\n                else "small"\n                if transcription_quality == "fast"\n                else "large-v3"\n            )\n            command = [\n                sys.executable,\n                "-m",\n                "accessible_caption_studio.whisper_worker",\n                "--model",\n                model_name,\n            ]\n            if transcription_language != "auto":\n                command.extend(["--language", language])\n            command.extend([str(channel_path), str(whisper_dir), str(words_path)])\n            process = subprocess.run(\n                command,\n                capture_output=True,\n                text=True,\n                check=False,\n            )\n',
)
replace(
    "src/accessible_caption_studio/overlap_worker.py",
    '    parser.add_argument("output_path", type=Path)\n    arguments = parser.parse_args()\n',
    '    parser.add_argument("output_path", type=Path)\n    parser.add_argument("transcription_language", nargs="?", default="en")\n    parser.add_argument("transcription_quality", nargs="?", default="accurate")\n    arguments = parser.parse_args()\n',
)
replace(
    "src/accessible_caption_studio/overlap_worker.py",
    '        arguments.references_path,\n        arguments.output_path,\n    )\n',
    '        arguments.references_path,\n        arguments.output_path,\n        arguments.transcription_language,\n        arguments.transcription_quality,\n    )\n',
)

# TTML / DFXP import and export.
replace(
    "src/accessible_caption_studio/captions.py",
    "import re\nfrom pathlib import Path\n",
    "import re\nimport xml.etree.ElementTree as ET\nfrom pathlib import Path\n",
)
replace(
    "src/accessible_caption_studio/captions.py",
    'def parse_caption_file(path: Path) -> list[CaptionCue]:\n    if path.suffix.lower() not in {".srt", ".vtt"}:\n        raise ValueError("captions must be an SRT or VTT file")\n    try:\n        return parse_caption_text(path.read_text(encoding="utf-8"))\n    except UnicodeDecodeError as exc:\n        raise ValueError("captions must use UTF-8 encoding") from exc\n',
    r'''def _ttml_seconds(value: str) -> float:
    cleaned = value.strip()
    if cleaned.endswith("ms"):
        return float(cleaned[:-2]) / 1000
    if cleaned.endswith("s"):
        return float(cleaned[:-1])
    parts = cleaned.split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    raise ValueError(f"unsupported TTML time expression: {value}")


def parse_ttml_text(content: str) -> list[CaptionCue]:
    try:
        root = ET.fromstring(content.lstrip("\ufeff"))
    except ET.ParseError as exc:
        raise ValueError("TTML captions contain invalid XML") from exc
    cues: list[CaptionCue] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "p":
            continue
        begin = element.attrib.get("begin")
        end = element.attrib.get("end")
        duration = element.attrib.get("dur")
        if not begin or (not end and not duration):
            continue
        try:
            start = _ttml_seconds(begin)
            finish = _ttml_seconds(end) if end else start + _ttml_seconds(duration or "0s")
        except (TypeError, ValueError) as exc:
            raise ValueError("TTML captions use an unsupported time expression") from exc
        text = " ".join("".join(element.itertext()).split()).strip()
        if not text:
            continue
        speaker = element.attrib.get("data-speaker")
        anonymous = _ANONYMOUS_SPEAKER.match(text)
        if not speaker and anonymous:
            speaker = anonymous.group(1)
            text = anonymous.group(2).strip()
        cues.append(
            CaptionCue(
                start=max(0, start),
                end=max(start, finish),
                text=text,
                speaker=speaker,
                source=SourceType.IMPORTED,
            )
        )
    if not cues:
        raise ValueError("no valid TTML caption cues were found")
    return cues


def parse_caption_file(path: Path) -> list[CaptionCue]:
    suffix = path.suffix.lower()
    if suffix not in {".srt", ".vtt", ".ttml", ".dfxp"}:
        raise ValueError("captions must be an SRT, VTT, TTML, or DFXP file")
    try:
        content = path.read_text(encoding="utf-8")
        return parse_ttml_text(content) if suffix in {".ttml", ".dfxp"} else parse_caption_text(content)
    except UnicodeDecodeError as exc:
        raise ValueError("captions must use UTF-8 encoding") from exc
''',
)
replace(
    "src/accessible_caption_studio/captions.py",
    '\ndef to_transcript_html(title: str, cues: list[CaptionCue]) -> str:\n',
    r'''

def _ttml_timestamp(value: float) -> str:
    total_ms = max(0, round(value * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def to_ttml(cues: list[CaptionCue], language: str = "en") -> str:
    namespace = "http://www.w3.org/ns/ttml"
    xml_namespace = "http://www.w3.org/XML/1998/namespace"
    ET.register_namespace("", namespace)
    root = ET.Element(f"{{{namespace}}}tt")
    root.set(f"{{{xml_namespace}}}lang", "und" if language == "auto" else language)
    body = ET.SubElement(root, f"{{{namespace}}}body")
    division = ET.SubElement(body, f"{{{namespace}}}div")
    for group in caption_groups(cues):
        cue = group[0]
        element = ET.SubElement(
            division,
            f"{{{namespace}}}p",
            {"begin": _ttml_timestamp(cue.start), "end": _ttml_timestamp(cue.end)},
        )
        element.text = "\n".join(cue_display_text(item) for item in group)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    ) + "\n"


def to_transcript_html(title: str, cues: list[CaptionCue]) -> str:
''',
)

write(
    "src/accessible_caption_studio/reports.py",
    r'''
    from __future__ import annotations

    import html
    from collections import Counter

    from .models import Project, Severity, SourceType
    from .validation import caption_style_readability_findings, validate_cues


    def _coverage(project: Project) -> float:
        if not project.media or project.media.duration <= 0 or not project.cues:
            return 0.0
        intervals = sorted((cue.start, cue.end) for cue in project.cues if cue.end > cue.start)
        covered = 0.0
        cursor = 0.0
        for start, end in intervals:
            if start >= cursor:
                covered += end - start
            elif end > cursor:
                covered += end - cursor
            cursor = max(cursor, end)
        return min(1.0, covered / project.media.duration)


    def _reading_speeds(project: Project) -> list[float]:
        values: list[float] = []
        for cue in project.cues:
            duration = cue.end - cue.start
            if duration > 0:
                values.append(len(cue.text.replace("\n", "")) / duration)
        return values


    def accessibility_report_html(project: Project) -> str:
        duration = project.media.duration if project.media else None
        findings = validate_cues(project.cues, duration)
        findings.extend(caption_style_readability_findings(project.caption_style))
        severities = Counter(finding.severity.value for finding in findings)
        speeds = _reading_speeds(project)
        average_speed = sum(speeds) / len(speeds) if speeds else 0.0
        maximum_speed = max(speeds, default=0.0)
        speakers = len({cue.speaker for cue in project.cues if cue.speaker})
        sound_cues = sum(1 for cue in project.cues if cue.source == SourceType.SOUND)
        low_confidence = sum(
            1
            for cue in project.cues
            if cue.source != SourceType.SOUND
            and cue.confidence is not None
            and cue.confidence < 0.75
        )
        cue_lookup = {cue.id: cue for cue in project.cues}

        rows = []
        for finding in findings:
            cue = cue_lookup.get(finding.cue_id or "")
            location = f"{cue.start:.3f}s" if cue else "Project"
            rows.append(
                "<tr>"
                f"<td>{html.escape(finding.severity.value.title())}</td>"
                f"<td>{html.escape(finding.code)}</td>"
                f"<td>{html.escape(location)}</td>"
                f"<td>{html.escape(finding.message)}</td>"
                "</tr>"
            )
        finding_rows = "".join(rows) or (
            '<tr><td colspan="4">No automatic authoring findings are currently open.</td></tr>'
        )
        language = project.transcription_language
        sdh = project.sdh_mode.title()
        safe_title = html.escape(project.name)
        return f"""<!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{safe_title} - Accessibility authoring report</title>
      <style>
        body{{font:16px/1.55 system-ui,sans-serif;max-width:72rem;margin:auto;padding:2rem;color:#172033}}
        h1,h2{{line-height:1.2}} .summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:.75rem}}
        .stat{{padding:.9rem;border:1px solid #d7deea;border-radius:.6rem}} .stat strong,.stat span{{display:block}}
        .stat strong{{font-size:1.35rem}} .stat span{{color:#526077}} table{{width:100%;border-collapse:collapse;margin-top:1rem}}
        th,td{{padding:.65rem;text-align:left;vertical-align:top;border-bottom:1px solid #d7deea}} th{{background:#f5f7fb}}
        .note{{padding:1rem;border-left:4px solid #2854d6;background:#eef4ff}} code{{overflow-wrap:anywhere}}
      </style>
    </head>
    <body><main>
      <p>Accessible Caption Studio</p>
      <h1>{safe_title} - Accessibility authoring report</h1>
      <p class="note">This is an authoring-quality report generated from the saved project. It is not a legal certification of WCAG, ADA, Section 508, or platform compliance.</p>
      <h2>Project summary</h2>
      <div class="summary">
        <div class="stat"><strong>{len(project.cues)}</strong><span>Caption cues</span></div>
        <div class="stat"><strong>{speakers}</strong><span>Speakers</span></div>
        <div class="stat"><strong>{sound_cues}</strong><span>Sound cues</span></div>
        <div class="stat"><strong>{low_confidence}</strong><span>Low-confidence cues</span></div>
        <div class="stat"><strong>{_coverage(project) * 100:.1f}%</strong><span>Timeline coverage</span></div>
        <div class="stat"><strong>{average_speed:.1f}</strong><span>Average characters/sec</span></div>
        <div class="stat"><strong>{maximum_speed:.1f}</strong><span>Maximum characters/sec</span></div>
        <div class="stat"><strong>{len(findings)}</strong><span>Open findings</span></div>
      </div>
      <p>Transcription language: <strong>{html.escape(language)}</strong>. Sound-caption mode: <strong>{html.escape(sdh)}</strong>.</p>
      <p>Findings by severity: {severities.get(Severity.ERROR.value, 0)} errors, {severities.get(Severity.WARNING.value, 0)} warnings, {severities.get(Severity.INFO.value, 0)} informational findings.</p>
      <h2>Outstanding authoring findings</h2>
      <table><thead><tr><th>Severity</th><th>Code</th><th>Location</th><th>Finding</th></tr></thead><tbody>{finding_rows}</tbody></table>
    </main></body></html>"""
    ''',
)

replace(
    "src/accessible_caption_studio/exports.py",
    "from .captions import to_srt, to_transcript_html, to_vtt\n",
    "from .captions import to_srt, to_transcript_html, to_ttml, to_vtt\n",
)
replace(
    "src/accessible_caption_studio/exports.py",
    "from .models import CaptionCue, CaptionStyle, ExportArtifact, Project\n",
    "from .models import CaptionCue, CaptionStyle, ExportArtifact, Project\nfrom .reports import accessibility_report_html\n",
)
replace(
    "src/accessible_caption_studio/exports.py",
    '    elif format_name == "html":\n        content, suffix = to_transcript_html(project.name, display_cues), ".html"\n    else:\n',
    '    elif format_name == "ttml":\n        content, suffix = to_ttml(display_cues, project.transcription_language), ".ttml"\n    elif format_name == "html":\n        content, suffix = to_transcript_html(project.name, display_cues), ".html"\n    elif format_name == "report":\n        content, suffix = accessibility_report_html(project), " - accessibility report.html"\n    else:\n',
)
replace(
    "src/accessible_caption_studio/exports.py",
    '    destination = exports / f"{base} - accessible captions{suffix}"\n',
    '    destination = (\n        exports / f"{base}{suffix}"\n        if format_name == "report"\n        else exports / f"{base} - accessible captions{suffix}"\n    )\n',
)

# Local video thumbnails.
write(
    "src/accessible_caption_studio/thumbnails.py",
    r'''
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
    ''',
)

# Individual model manager and background preloading.
write(
    "src/accessible_caption_studio/model_management.py",
    r'''
    from __future__ import annotations

    import json
    import shutil
    import subprocess
    import sys
    import threading
    from pathlib import Path

    from .models import path_size, utc_now


    MODEL_SPECS = (
        ("whisper-en-fast", "Whisper English - Fast", "Small English transcription model"),
        ("whisper-en-accurate", "Whisper English - Accurate", "Distil-Whisper Large v3 transcription model"),
        ("whisper-multilingual-fast", "Whisper Multilingual - Fast", "Small multilingual Whisper model"),
        ("whisper-multilingual-accurate", "Whisper Multilingual - Accurate", "Large v3 multilingual Whisper model"),
        ("speaker-ecapa", "ECAPA speaker labeling", "Anonymous local voice embeddings"),
        ("speaker-wavlm", "WavLM voice matching", "Supporting voice matching for overlap analysis"),
        ("sound-ast", "AST sound recognition", "Meaningful non-speech sound detection"),
        ("overlap-sepformer", "SepFormer overlap separation", "Two-speaker separation for selected intervals"),
        ("face-yunet-sface", "YuNet + SFace", "Anonymous local face detection and matching"),
    )


    class ModelManager:
        def __init__(self, root: Path) -> None:
            self.root = root
            self.root.mkdir(parents=True, exist_ok=True)
            self.marker_dir = self.root / ".managed"
            self.marker_dir.mkdir(exist_ok=True)
            self._lock = threading.RLock()
            self._status: dict[str, str] = {}
            self._errors: dict[str, str] = {}

        @staticmethod
        def ids() -> set[str]:
            return {item[0] for item in MODEL_SPECS}

        def list(self) -> list[dict[str, object]]:
            rows = []
            with self._lock:
                for model_id, label, description in MODEL_SPECS:
                    paths = self._paths(model_id)
                    installed = bool(paths) or self._marker(model_id).is_file()
                    rows.append(
                        {
                            "id": model_id,
                            "label": label,
                            "description": description,
                            "installed": installed,
                            "size_bytes": self._size(paths),
                            "status": self._status.get(
                                model_id, "installed" if installed else "not_installed"
                            ),
                            "error": self._errors.get(model_id),
                        }
                    )
            return rows

        def install(self, model_id: str) -> dict[str, object]:
            self._require(model_id)
            with self._lock:
                if self._status.get(model_id) == "installing":
                    return self._record(model_id)
                self._status[model_id] = "installing"
                self._errors.pop(model_id, None)
            threading.Thread(target=self._run_install, args=(model_id,), daemon=True).start()
            return self._record(model_id)

        def remove(self, model_id: str) -> dict[str, object]:
            self._require(model_id)
            with self._lock:
                if self._status.get(model_id) == "installing":
                    raise ValueError("Wait for the model download to finish before removing it")
                for path in self._paths(model_id):
                    if path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        path.unlink(missing_ok=True)
                self._marker(model_id).unlink(missing_ok=True)
                self._status[model_id] = "not_installed"
                self._errors.pop(model_id, None)
            return self._record(model_id)

        def _run_install(self, model_id: str) -> None:
            command = [
                sys.executable,
                "-m",
                "accessible_caption_studio.model_worker",
                model_id,
                str(self.root),
            ]
            process = subprocess.run(command, capture_output=True, text=True, check=False)
            with self._lock:
                if process.returncode:
                    detail = (process.stderr or process.stdout or "Model download failed").strip()
                    self._status[model_id] = "error"
                    self._errors[model_id] = detail[-900:]
                else:
                    self._status[model_id] = "installed"
                    self._errors.pop(model_id, None)
                    self._marker(model_id).write_text(
                        json.dumps({"installed_at": utc_now().isoformat()}), encoding="utf-8"
                    )

        def _record(self, model_id: str) -> dict[str, object]:
            return next(item for item in self.list() if item["id"] == model_id)

        def _require(self, model_id: str) -> None:
            if model_id not in self.ids():
                raise KeyError(model_id)

        def _marker(self, model_id: str) -> Path:
            return self.marker_dir / f"{model_id}.json"

        @staticmethod
        def _size(paths: list[Path]) -> int:
            files: set[Path] = set()
            total = 0
            for path in paths:
                if path.is_file():
                    files.add(path)
                elif path.is_dir():
                    files.update(item for item in path.rglob("*") if item.is_file())
            for path in files:
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
            return total

        def _paths(self, model_id: str) -> list[Path]:
            exact = {
                "speaker-ecapa": [self.root / "ecapa-voxceleb"],
                "speaker-wavlm": [self.root / "huggingface" / "models--microsoft--wavlm-base-plus-sv"],
                "sound-ast": [self.root / "huggingface" / "models--MIT--ast-finetuned-audioset-10-10-0.4593"],
                "overlap-sepformer": [self.root / "speechbrain" / "sepformer-whamr16k"],
                "face-yunet-sface": [self.root / "opencv-face"],
            }
            if model_id in exact:
                return [path for path in exact[model_id] if path.exists()]
            whisper = self.root / "whisper"
            if not whisper.is_dir():
                return []
            matches: list[Path] = []
            for path in whisper.iterdir():
                name = path.name.casefold().replace("_", "-")
                is_distil = "distil" in name and "large-v3" in name
                is_large = "large-v3" in name and not is_distil
                is_small_en = "small.en" in name or "small-en" in name
                is_small = "small" in name and not is_small_en
                wanted = {
                    "whisper-en-fast": is_small_en,
                    "whisper-en-accurate": is_distil,
                    "whisper-multilingual-fast": is_small,
                    "whisper-multilingual-accurate": is_large,
                }.get(model_id, False)
                if wanted:
                    matches.append(path)
            return matches
    ''',
)

write(
    "src/accessible_caption_studio/model_worker.py",
    r'''
    from __future__ import annotations

    import argparse
    from pathlib import Path


    def _patch_speechbrain_torch() -> None:
        import torch

        if hasattr(torch.amp, "custom_fwd"):
            return

        def compatible_custom_fwd(function=None, *, device_type: str, cast_inputs=None):
            if function is None:
                return lambda wrapped: compatible_custom_fwd(
                    wrapped, device_type=device_type, cast_inputs=cast_inputs
                )
            if device_type == "cuda":
                return torch.cuda.amp.custom_fwd(function, cast_inputs=cast_inputs)
            return function

        torch.amp.custom_fwd = compatible_custom_fwd


    def install(model_id: str, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        whisper_models = {
            "whisper-en-fast": "small.en",
            "whisper-en-accurate": "distil-large-v3",
            "whisper-multilingual-fast": "small",
            "whisper-multilingual-accurate": "large-v3",
        }
        if model_id in whisper_models:
            from faster_whisper import WhisperModel

            WhisperModel(
                whisper_models[model_id],
                device="cpu",
                compute_type="int8",
                download_root=str(root / "whisper"),
            )
            return
        if model_id == "speaker-ecapa":
            _patch_speechbrain_torch()
            from speechbrain.inference.classifiers import EncoderClassifier
            from speechbrain.utils.fetching import FetchConfig, LocalStrategy

            EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=str(root / "ecapa-voxceleb"),
                run_opts={"device": "cpu"},
                local_strategy=LocalStrategy.COPY,
                fetch_config=FetchConfig(
                    revision="0f99f2d0ebe89ac095bcc5903c4dd8f72b367286"
                ),
            )
            return
        if model_id == "speaker-wavlm":
            from transformers import Wav2Vec2FeatureExtractor, WavLMForXVector

            model_name = "microsoft/wavlm-base-plus-sv"
            revision = "a0bfa70fc99be91689cfb6a9453c3cba66345df0"
            cache = str(root / "huggingface")
            Wav2Vec2FeatureExtractor.from_pretrained(
                model_name, revision=revision, cache_dir=cache
            )
            WavLMForXVector.from_pretrained(
                model_name,
                revision=revision,
                cache_dir=cache,
                use_safetensors=True,
            )
            return
        if model_id == "sound-ast":
            from transformers import ASTForAudioClassification, AutoFeatureExtractor

            model_name = "MIT/ast-finetuned-audioset-10-10-0.4593"
            cache = str(root / "huggingface")
            AutoFeatureExtractor.from_pretrained(model_name, cache_dir=cache)
            ASTForAudioClassification.from_pretrained(model_name, cache_dir=cache)
            return
        if model_id == "overlap-sepformer":
            _patch_speechbrain_torch()
            from speechbrain.inference.separation import SepformerSeparation

            SepformerSeparation.from_hparams(
                source="speechbrain/sepformer-whamr16k",
                savedir=str(root / "speechbrain" / "sepformer-whamr16k"),
                run_opts={"device": "cpu"},
            )
            return
        if model_id == "face-yunet-sface":
            from .visual_worker import (
                SFACE_NAME,
                SFACE_SHA256,
                YUNET_NAME,
                YUNET_SHA256,
                _ensure_model,
            )

            directory = root / "opencv-face"
            _ensure_model(directory, YUNET_NAME, "face_detection_yunet", YUNET_SHA256)
            _ensure_model(directory, SFACE_NAME, "face_recognition_sface", SFACE_SHA256)
            return
        raise ValueError(f"Unknown managed model: {model_id}")


    def main() -> None:
        parser = argparse.ArgumentParser()
        parser.add_argument("model_id")
        parser.add_argument("root", type=Path)
        arguments = parser.parse_args()
        install(arguments.model_id, arguments.root)


    if __name__ == "__main__":
        main()
    ''',
)

write(
    "src/accessible_caption_studio/roadmap.py",
    r'''
    from __future__ import annotations

    from collections.abc import Callable
    from typing import Any, Literal

    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from pydantic import BaseModel, Field

    from .jobs import JobManager
    from .media import download_youtube, inspect_media
    from .model_management import ModelManager
    from .models import AnalysisJob, JobState, Project
    from .storage import ProjectStore, safe_filename
    from .thumbnails import ensure_project_thumbnail


    class ProjectPreferences(BaseModel):
        transcription_language: str = Field(
            default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"
        )
        sdh_mode: Literal["off", "conservative", "full"] = "full"


    RetryHandler = Callable[[str, AnalysisJob], Any]


    def register_roadmap_routes(
        app: FastAPI,
        store: ProjectStore,
        jobs: JobManager,
        retry_handlers: dict[str, RetryHandler],
        analysis_task: Callable[[str, ProjectStore, Any], None],
    ) -> None:
        manager = ModelManager(store.models_dir)
        app.state.model_manager = manager

        @app.patch("/api/projects/{project_id}/preferences")
        def update_project_preferences(
            project_id: str, request: ProjectPreferences
        ) -> Project:
            try:
                project = store.get(project_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Project not found") from exc
            changed = (
                project.transcription_language != request.transcription_language
                or project.sdh_mode != request.sdh_mode
            )
            if changed:
                store.create_revision(project, "Before changing transcription options")
                project.transcription_language = request.transcription_language
                project.sdh_mode = request.sdh_mode
            return store.save(project) if changed else project

        @app.get("/api/projects/{project_id}/thumbnail")
        def project_thumbnail(project_id: str) -> FileResponse:
            try:
                project = store.get(project_id)
                path = ensure_project_thumbnail(project, store.project_dir(project_id))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Project not found") from exc
            if path is None:
                raise HTTPException(status_code=404, detail="This project has no video thumbnail")
            return FileResponse(
                path,
                media_type="image/jpeg",
                headers={"Cache-Control": "private, max-age=3600"},
            )

        @app.get("/api/models")
        def models() -> list[dict[str, object]]:
            return manager.list()

        @app.post("/api/models/{model_id}/install", status_code=202)
        def install_model(model_id: str) -> dict[str, object]:
            try:
                return manager.install(model_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Unknown model") from exc

        @app.delete("/api/models/{model_id}")
        def remove_model(model_id: str) -> dict[str, object]:
            try:
                return manager.remove(model_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Unknown model") from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

        @app.post("/api/projects/{project_id}/jobs/{job_id}/retry", status_code=202)
        def retry_job(project_id: str, job_id: str) -> Any:
            try:
                previous = jobs.get(project_id, job_id)
                project = store.get(project_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="Job or project not found") from exc
            if previous.state != JobState.FAILED:
                raise HTTPException(status_code=409, detail="Only failed or interrupted jobs can be retried")

            if previous.kind == "youtube-analysis":
                parameters = dict(previous.parameters or {})
                url = str(parameters.get("url") or "").strip()
                if not url:
                    raise HTTPException(
                        status_code=400,
                        detail="This older YouTube job did not save enough information to retry. Import the link again.",
                    )

                def target(_job: Any, progress: Any) -> None:
                    progress("Downloading", 5, "Downloading the selected YouTube video")
                    project_dir = store.project_dir(project_id)
                    source, title = download_youtube(
                        url,
                        project_dir,
                        progress,
                        cookie_browser=parameters.get("cookie_browser") or None,
                    )
                    final_name = safe_filename(f"{title}{source.suffix}")
                    final_path = project_dir / final_name
                    source.replace(final_path)
                    current = store.get(project_id)
                    current.name = title
                    current.media = inspect_media(final_path, source_url=url)
                    current.media.stored_name = final_name
                    current.transcription_quality = str(
                        parameters.get("transcription_quality") or current.transcription_quality
                    )
                    current.transcription_language = str(
                        parameters.get("transcription_language") or current.transcription_language
                    )
                    mode = str(parameters.get("sdh_mode") or current.sdh_mode)
                    current.sdh_mode = mode if mode in {"off", "conservative", "full"} else "full"
                    store.save(current)
                    analysis_task(project_id, store, progress)

                retried = jobs.start(
                    project_id,
                    "youtube-analysis",
                    target,
                    parameters=parameters,
                )
            else:
                handler = retry_handlers.get(previous.kind)
                if handler is None:
                    raise HTTPException(
                        status_code=400,
                        detail="This job cannot be reconstructed automatically. Restart it from its original project control.",
                    )
                if previous.kind == "overlap-analysis" and not {
                    "start",
                    "end",
                }.issubset(previous.parameters):
                    raise HTTPException(
                        status_code=400,
                        detail="This older overlap job did not save its selected interval. Start overlap analysis again from the caption.",
                    )
                retried = handler(project_id, previous)

            if isinstance(retried, AnalysisJob):
                project = store.get(project_id)
                project.latest_job_id = retried.id
                store.save(project)
            return retried
    ''',
)

# Wire final-roadmap services into the existing FastAPI app with minimal changes.
replace(
    "src/accessible_caption_studio/webapp.py",
    "from .analyzer import LocalAnalyzer\n",
    "from .enhanced_analyzer import LocalAnalyzer\n",
)
replace(
    "src/accessible_caption_studio/webapp.py",
    "from .media import download_youtube, extract_audio, inspect_media\n",
    "from .media import download_youtube, extract_audio, inspect_media\nfrom .roadmap import register_roadmap_routes\n",
)
replace(
    "src/accessible_caption_studio/webapp.py",
    'class YouTubeRequest(BaseModel):\n    url: str\n    cookie_browser: Literal["brave", "chrome", "edge", "firefox", "safari"] | None = None\n    transcription_quality: Literal["fast", "accurate"] = "accurate"\n',
    'class YouTubeRequest(BaseModel):\n    url: str\n    cookie_browser: Literal["brave", "chrome", "edge", "firefox", "safari"] | None = None\n    transcription_quality: Literal["fast", "accurate"] = "accurate"\n    transcription_language: str = Field(\n        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"\n    )\n    sdh_mode: Literal["off", "conservative", "full"] = "full"\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '    transcription_quality: Literal["fast", "accurate"] | None = None\n    caption_style: CaptionStyle | None = None\n',
    '    transcription_quality: Literal["fast", "accurate"] | None = None\n    transcription_language: str | None = Field(\n        default=None, pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"\n    )\n    sdh_mode: Literal["off", "conservative", "full"] | None = None\n    caption_style: CaptionStyle | None = None\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '    @app.get("/app.js")\n    def script() -> Response:\n        return Response(_asset_text("app.js"), media_type="text/javascript")\n',
    '    @app.get("/app.js")\n    def script() -> Response:\n        return Response(_asset_text("app.js"), media_type="text/javascript")\n\n    @app.get("/final-batch.js")\n    def final_batch_script() -> Response:\n        return Response(_asset_text("final_batch.js"), media_type="text/javascript")\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        transcription_quality: Annotated[Literal["fast", "accurate"], Form()] = "accurate",\n    ) -> dict[str, Any]:\n',
    '        transcription_quality: Annotated[Literal["fast", "accurate"], Form()] = "accurate",\n        transcription_language: Annotated[\n            str, Form(pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$")\n        ] = "en",\n        sdh_mode: Annotated[Literal["off", "conservative", "full"], Form()] = "full",\n    ) -> dict[str, Any]:\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        project.transcription_quality = transcription_quality\n        project_dir = store.project_dir(project.id)\n',
    '        project.transcription_quality = transcription_quality\n        project.transcription_language = transcription_language\n        project.sdh_mode = sdh_mode\n        project_dir = store.project_dir(project.id)\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        project.transcription_quality = request.transcription_quality\n        store.save(project)\n',
    '        project.transcription_quality = request.transcription_quality\n        project.transcription_language = request.transcription_language\n        project.sdh_mode = request.sdh_mode\n        store.save(project)\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        job = jobs.start(project.id, "youtube-analysis", target)\n',
    '        job = jobs.start(\n            project.id,\n            "youtube-analysis",\n            target,\n            parameters={\n                "url": request.url,\n                "cookie_browser": request.cookie_browser,\n                "transcription_quality": request.transcription_quality,\n                "transcription_language": request.transcription_language,\n                "sdh_mode": request.sdh_mode,\n            },\n        )\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '            or (\n                request.caption_style is not None\n                and request.caption_style != project.caption_style\n            )\n',
    '            or (\n                request.transcription_language is not None\n                and request.transcription_language != project.transcription_language\n            )\n            or (request.sdh_mode is not None and request.sdh_mode != project.sdh_mode)\n            or (\n                request.caption_style is not None\n                and request.caption_style != project.caption_style\n            )\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        if request.transcription_quality is not None:\n            project.transcription_quality = request.transcription_quality\n        if request.caption_style is not None:\n',
    '        if request.transcription_quality is not None:\n            project.transcription_quality = request.transcription_quality\n        if request.transcription_language is not None:\n            project.transcription_language = request.transcription_language\n        if request.sdh_mode is not None:\n            project.sdh_mode = request.sdh_mode\n        if request.caption_style is not None:\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        job = jobs.start(project_id, "overlap-analysis", target)\n',
    '        job = jobs.start(\n            project_id,\n            "overlap-analysis",\n            target,\n            parameters={"start": request.start, "end": request.end},\n        )\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        return jobs.start(project_id, "speaker-reanalysis", target)\n',
    '        return jobs.start(\n            project_id,\n            "speaker-reanalysis",\n            target,\n            parameters={"expected_speaker_count": request.expected_speaker_count},\n        )\n',
)
replace_all(
    "src/accessible_caption_studio/webapp.py",
    "LocalAnalyzer(store.models_dir, current.transcription_quality)",
    "LocalAnalyzer(\n                store.models_dir,\n                current.transcription_quality,\n                current.transcription_language,\n                current.sdh_mode,\n            )",
)
replace(
    "src/accessible_caption_studio/webapp.py",
    "analyzer = LocalAnalyzer(store.models_dir, project.transcription_quality)\n",
    "analyzer = LocalAnalyzer(\n        store.models_dir,\n        project.transcription_quality,\n        project.transcription_language,\n        project.sdh_mode,\n    )\n",
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '        if format_name in {"srt", "vtt", "html"}:\n',
    '        if format_name in {"srt", "vtt", "ttml", "html", "report"}:\n',
)
replace(
    "src/accessible_caption_studio/webapp.py",
    '    @app.delete("/api/storage/{target}", status_code=204)\n    def clear_storage(target: str) -> Response:\n        try:\n            store.clear_cache(target)\n        except ValueError as exc:\n            raise HTTPException(status_code=400, detail=str(exc)) from exc\n        return Response(status_code=204)\n\n    return app\n',
    '    @app.delete("/api/storage/{target}", status_code=204)\n    def clear_storage(target: str) -> Response:\n        try:\n            store.clear_cache(target)\n        except ValueError as exc:\n            raise HTTPException(status_code=400, detail=str(exc)) from exc\n        return Response(status_code=204)\n\n    register_roadmap_routes(\n        app,\n        store,\n        jobs,\n        {\n            "analysis": lambda project_id, _job: analyze_project(project_id),\n            "mp4-export": lambda project_id, _job: create_export(project_id, "mp4"),\n            "transcript-repair": lambda project_id, _job: repair_transcript(project_id),\n            "speaker-reanalysis": lambda project_id, job: reanalyze_speakers(\n                project_id,\n                SpeakerReanalysisRequest(\n                    expected_speaker_count=job.parameters.get("expected_speaker_count")\n                ),\n            ),\n            "overlap-analysis": lambda project_id, job: analyze_overlap(\n                project_id,\n                OverlapRequest(\n                    start=float(job.parameters["start"]), end=float(job.parameters["end"])\n                ),\n            ),\n        },\n        _analysis_task,\n    )\n\n    return app\n',
)

# Extend the caption picker and load the final-batch UI enhancement script.
replace(
    "src/accessible_caption_studio/web/index.html",
    '              <label for="captionInput"><strong>Already have captions?</strong> <span>Optional SRT or VTT</span></label>\n              <input id="captionInput" name="captions" type="file" accept=".srt,.vtt,text/vtt">\n',
    '              <label for="captionInput"><strong>Already have captions?</strong> <span>Optional SRT, VTT, TTML, or DFXP</span></label>\n              <input id="captionInput" name="captions" type="file" accept=".srt,.vtt,.ttml,.dfxp,text/vtt,application/ttml+xml">\n',
)
replace(
    "src/accessible_caption_studio/web/index.html",
    '  <script src="/app.js"></script>\n',
    '  <script src="/app.js"></script>\n  <script src="/final-batch.js"></script>\n',
)

write(
    "src/accessible_caption_studio/web/final_batch.js",
    r'''
    (() => {
      const languageStorageKey = "accessible-caption-transcription-language";
      const sdhStorageKey = "accessible-caption-sdh-mode";
      const languages = [
        ["auto", "Auto-detect"], ["en", "English"], ["es", "Spanish"], ["fr", "French"],
        ["de", "German"], ["it", "Italian"], ["pt", "Portuguese"], ["nl", "Dutch"],
        ["pl", "Polish"], ["ru", "Russian"], ["uk", "Ukrainian"], ["zh", "Chinese"],
        ["ja", "Japanese"], ["ko", "Korean"], ["ar", "Arabic"], ["hi", "Hindi"],
        ["tr", "Turkish"], ["vi", "Vietnamese"], ["id", "Indonesian"], ["th", "Thai"],
      ];
      const sdhModes = [
        ["off", "Off", "Do not add automatic non-speech sound captions."],
        ["conservative", "Conservative", "Add only higher-confidence meaningful sounds."],
        ["full", "Full SDH", "Use the complete accessibility-focused sound-caption workflow."],
      ];
      let modelPollTimer = null;

      function readPreference(key, fallback) {
        try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
      }
      function writePreference(key, value) {
        try { localStorage.setItem(key, value); } catch (_) { /* Session choice still works. */ }
      }
      function defaultPreferences() {
        const language = readPreference(languageStorageKey, "en");
        const sdhMode = readPreference(sdhStorageKey, "full");
        return {
          transcription_language: languages.some(([code]) => code === language) ? language : "en",
          sdh_mode: sdhModes.some(([code]) => code === sdhMode) ? sdhMode : "full",
        };
      }
      function languageLabel(code) {
        return languages.find(([value]) => value === code)?.[1] || code;
      }
      function sdhLabel(code) {
        return sdhModes.find(([value]) => value === code)?.[1] || code;
      }

      const nativeFetch = window.fetch.bind(window);
      window.fetch = function fetchWithCaptioningPreferences(input, init = {}) {
        const url = typeof input === "string" ? input : input?.url || "";
        const preferences = defaultPreferences();
        if (url.endsWith("/api/projects/upload") && init.body instanceof FormData) {
          if (!init.body.has("transcription_language")) init.body.set("transcription_language", preferences.transcription_language);
          if (!init.body.has("sdh_mode")) init.body.set("sdh_mode", preferences.sdh_mode);
        }
        if (url.endsWith("/api/projects/youtube") && typeof init.body === "string") {
          try {
            const body = JSON.parse(init.body);
            body.transcription_language ??= preferences.transcription_language;
            body.sdh_mode ??= preferences.sdh_mode;
            init = { ...init, body: JSON.stringify(body) };
          } catch (_) { /* Leave unrelated JSON untouched. */ }
        }
        return nativeFetch(input, init);
      };

      function optionMarkup(items) {
        return items.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
      }

      function installStyles() {
        if (document.querySelector("#finalRoadmapStyles")) return;
        const style = document.createElement("style");
        style.id = "finalRoadmapStyles";
        style.textContent = `
          .captioning-options { margin: .8rem 0 .15rem; border-top: 1px solid var(--soft-line); border-bottom: 1px solid var(--soft-line); }
          .captioning-options summary { display:flex; align-items:center; justify-content:space-between; gap:.75rem; padding:.65rem .1rem; cursor:pointer; color:var(--ink); font-size:.8rem; font-weight:800; }
          .captioning-options summary span { color:var(--muted); font-size:.72rem; font-weight:700; }
          .captioning-options-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.75rem; padding:0 .1rem .8rem; }
          .captioning-options-grid label, .project-preference-card label { display:grid; gap:.35rem; color:var(--ink); font-size:.78rem; font-weight:750; }
          .captioning-options-grid select, .project-preference-card select { width:100%; border:1px solid #aeb9ce; border-radius:9px; padding:.58rem .65rem; color:var(--ink); background:var(--control); }
          .captioning-options-note { grid-column:1/-1; margin:0; color:var(--muted); font-size:.72rem; line-height:1.45; }
          .project-thumbnail { width:72px; height:46px; object-fit:cover; border-radius:8px; border:1px solid var(--line); background:var(--wash); grid-row:1 / span 3; }
          .project-card .project-open:has(.project-thumbnail) { display:grid; grid-template-columns:72px auto minmax(0,1fr); column-gap:.7rem; align-items:center; }
          .project-card .project-open:has(.project-thumbnail) .project-type { grid-column:2; }
          .project-card .project-open:has(.project-thumbnail) strong, .project-card .project-open:has(.project-thumbnail) > span:not(.project-type):not(.project-job-status) { grid-column:3; }
          .model-manager-details { border-top:1px solid var(--line); padding-top:.75rem; }
          .model-manager-details > summary { cursor:pointer; font-weight:800; }
          .model-manager-copy { margin:.4rem 0 .7rem; color:var(--muted); font-size:.78rem; }
          .model-manager-list { display:grid; gap:.45rem; }
          .model-manager-row { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:.75rem; padding:.65rem .7rem; border-radius:9px; background:var(--wash); }
          .model-manager-row > div { min-width:0; display:grid; gap:.12rem; }
          .model-manager-row strong { font-size:.78rem; }
          .model-manager-row span { color:var(--muted); font-size:.7rem; overflow-wrap:anywhere; }
          .model-manager-row button { min-height:32px; padding:.35rem .55rem; }
          .model-manager-error { color:var(--danger) !important; }
          .project-preference-dialog { width:min(520px,calc(100vw - 2rem)); }
          .project-preference-card { display:grid; gap:.8rem; }
          .export-grid [data-export="report"] { border-color:color-mix(in srgb,var(--blue) 28%,var(--line)); }
          @media (max-width:560px) {
            .captioning-options-grid { grid-template-columns:1fr; }
            .captioning-options-note { grid-column:1; }
            .project-card .project-open:has(.project-thumbnail) { grid-template-columns:58px auto minmax(0,1fr); }
            .project-thumbnail { width:58px; height:42px; }
            .model-manager-row { grid-template-columns:1fr; }
            .model-manager-row button { width:100%; }
          }
          @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { animation-duration:.01ms !important; animation-iteration-count:1 !important; transition-duration:.01ms !important; scroll-behavior:auto !important; }
          }
          @media (forced-colors: active) {
            .project-card, .model-manager-row, .captioning-options, .waveform-canvas-wrap { border:1px solid CanvasText; }
            button, input, select, summary { forced-color-adjust:auto; }
          }
        `;
        document.head.append(style);
      }

      function installImportOptions() {
        if (document.querySelector("#captioningOptions")) return;
        const tabs = document.querySelector(".import-card .tabs");
        if (!tabs) return;
        const details = document.createElement("details");
        details.id = "captioningOptions";
        details.className = "captioning-options";
        details.innerHTML = `
          <summary>Captioning options <span id="captioningOptionsSummary"></span></summary>
          <div class="captioning-options-grid">
            <label for="defaultTranscriptionLanguage">Language<select id="defaultTranscriptionLanguage">${optionMarkup(languages)}</select></label>
            <label for="defaultSdhMode">Sound captions<select id="defaultSdhMode">${optionMarkup(sdhModes)}</select></label>
            <p class="captioning-options-note">Auto-detect and non-English choices use multilingual Whisper models. These defaults apply to new automatic analyses and stay on this computer.</p>
          </div>`;
        tabs.after(details);
        const preferences = defaultPreferences();
        details.querySelector("#defaultTranscriptionLanguage").value = preferences.transcription_language;
        details.querySelector("#defaultSdhMode").value = preferences.sdh_mode;
        const update = () => {
          const language = details.querySelector("#defaultTranscriptionLanguage").value;
          const sdh = details.querySelector("#defaultSdhMode").value;
          writePreference(languageStorageKey, language);
          writePreference(sdhStorageKey, sdh);
          details.querySelector("#captioningOptionsSummary").textContent = `${languageLabel(language)} · ${sdhLabel(sdh)}`;
        };
        details.querySelectorAll("select").forEach((select) => select.addEventListener("change", update));
        update();
      }

      function installProjectPreferenceDialog() {
        if (document.querySelector("#projectPreferenceDialog")) return;
        const dialog = document.createElement("dialog");
        dialog.id = "projectPreferenceDialog";
        dialog.className = "project-preference-dialog";
        dialog.setAttribute("aria-labelledby", "projectPreferenceTitle");
        dialog.innerHTML = `
          <form id="projectPreferenceForm" class="dialog-card project-preference-card">
            <div class="dialog-heading"><div><p class="eyebrow">Automatic analysis</p><h2 id="projectPreferenceTitle">Transcription options</h2></div><button id="closeProjectPreferences" class="icon-button" type="button" aria-label="Close transcription options">×</button></div>
            <p class="field-note">These options are saved with this project. Run analysis again after changing them to regenerate automatic captions.</p>
            <label for="projectTranscriptionLanguage">Language<select id="projectTranscriptionLanguage">${optionMarkup(languages)}</select></label>
            <label for="projectSdhMode">Sound captions<select id="projectSdhMode">${optionMarkup(sdhModes)}</select></label>
            <div class="button-row dialog-actions"><span class="dialog-action-spacer"></span><button id="cancelProjectPreferences" class="secondary" type="button">Cancel</button><button class="primary" type="submit">Save options</button></div>
          </form>`;
        document.body.append(dialog);
        dialog.querySelector("#closeProjectPreferences").addEventListener("click", () => dialog.close());
        dialog.querySelector("#cancelProjectPreferences").addEventListener("click", () => dialog.close());
        dialog.querySelector("#projectPreferenceForm").addEventListener("submit", saveProjectPreferences);
      }

      function installProjectPreferenceAction() {
        const more = document.querySelector(".editor-more-popover");
        if (!more || document.querySelector("#projectPreferenceButton")) return;
        const button = document.createElement("button");
        button.id = "projectPreferenceButton";
        button.className = "secondary editor-action editor-more-action";
        button.type = "button";
        button.textContent = "Transcription options";
        button.addEventListener("click", () => {
          if (!state.project) return;
          document.querySelector("#projectTranscriptionLanguage").value = state.project.transcription_language || "en";
          document.querySelector("#projectSdhMode").value = state.project.sdh_mode || "full";
          document.querySelector("#projectPreferenceDialog").showModal();
        });
        more.append(button);
      }

      async function saveProjectPreferences(event) {
        event.preventDefault();
        if (!state.project) return;
        const submit = event.currentTarget.querySelector('button[type="submit"]');
        submit.disabled = true;
        try {
          const project = await api(`/api/projects/${state.project.id}/preferences`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              transcription_language: document.querySelector("#projectTranscriptionLanguage").value,
              sdh_mode: document.querySelector("#projectSdhMode").value,
            }),
          });
          state.project = project;
          document.querySelector("#projectPreferenceDialog").close();
          toast("Transcription options saved. Run analysis again to apply them to automatic captions.");
        } catch (error) {
          toast(error.message, "error");
        } finally {
          submit.disabled = false;
        }
      }

      function installExportOptions() {
        const grid = document.querySelector("#exportDialog .export-grid");
        if (!grid) return;
        const add = (format, title, description) => {
          if (grid.querySelector(`[data-export="${format}"]`)) return;
          const button = document.createElement("button");
          button.type = "button";
          button.dataset.export = format;
          button.innerHTML = `<strong>${title}</strong><span>${description}</span>`;
          button.addEventListener("click", () => createExport(format));
          grid.append(button);
        };
        add("ttml", "TTML captions", "Timed Text format for broadcast and enterprise workflows");
        add("report", "Accessibility report", "Saved authoring findings, statistics, and review status");
      }

      const previousRenderProjectsFinal = renderProjects;
      renderProjects = function renderProjectsWithThumbnails() {
        previousRenderProjectsFinal();
        document.querySelectorAll(".project-card[data-project-id]").forEach((card) => {
          const project = state.projects.find((item) => String(item.id) === String(card.dataset.projectId));
          if (!project?.media?.has_video || card.querySelector(".project-thumbnail")) return;
          const image = document.createElement("img");
          image.className = "project-thumbnail";
          image.alt = "";
          image.loading = "lazy";
          image.src = `/api/projects/${encodeURIComponent(project.id)}/thumbnail`;
          image.addEventListener("error", () => image.remove(), { once: true });
          card.querySelector(".project-open")?.prepend(image);
        });
      };

      function installModelManager() {
        if (document.querySelector("#modelManagerSection")) return;
        const readiness = document.querySelector("#systemReadiness");
        const storageSection = [...document.querySelectorAll("#settingsDialog .dialog-card > section")].find(
          (section) => section.querySelector("h3")?.textContent?.trim() === "Storage"
        );
        const section = document.createElement("section");
        section.id = "modelManagerSection";
        section.innerHTML = `
          <details class="model-manager-details">
            <summary>Model manager</summary>
            <p class="model-manager-copy">Inspect, preload, or remove individual local models. Downloads stay in the studio model cache.</p>
            <div id="modelManagerList" class="model-manager-list" role="status"></div>
          </details>`;
        if (readiness) readiness.after(section);
        else if (storageSection) storageSection.before(section);
        else document.querySelector("#settingsDialog .dialog-card")?.append(section);
        section.querySelector("details").addEventListener("toggle", (event) => {
          if (event.currentTarget.open) loadModels();
          else clearTimeout(modelPollTimer);
        });
      }

      async function loadModels() {
        const list = document.querySelector("#modelManagerList");
        if (!list) return;
        try {
          const models = await api("/api/models");
          renderModels(models);
          clearTimeout(modelPollTimer);
          if (models.some((model) => model.status === "installing")) {
            modelPollTimer = setTimeout(loadModels, 1600);
          }
        } catch (error) {
          list.textContent = `Model status unavailable: ${error.message}`;
        }
      }

      function renderModels(models) {
        const list = document.querySelector("#modelManagerList");
        list.replaceChildren();
        models.forEach((model) => {
          const row = document.createElement("div");
          row.className = "model-manager-row";
          const copy = document.createElement("div");
          const title = document.createElement("strong");
          title.textContent = model.label;
          const status = document.createElement("span");
          const size = model.size_bytes ? formatBytes(model.size_bytes) : "No local files";
          status.textContent = model.status === "installing" ? `Downloading · ${size}` : model.installed ? `Installed · ${size}` : size;
          copy.append(title, status);
          if (model.error) {
            const error = document.createElement("span");
            error.className = "model-manager-error";
            error.textContent = model.error;
            copy.append(error);
          }
          const button = document.createElement("button");
          button.type = "button";
          button.className = model.installed ? "danger-secondary" : "secondary";
          button.disabled = model.status === "installing";
          button.textContent = model.status === "installing" ? "Downloading…" : model.installed ? "Remove" : "Preload";
          button.addEventListener("click", () => changeModel(model, button));
          row.append(copy, button);
          list.append(row);
        });
      }

      async function changeModel(model, button) {
        button.disabled = true;
        try {
          await api(`/api/models/${encodeURIComponent(model.id)}${model.installed ? "" : "/install"}`, {
            method: model.installed ? "DELETE" : "POST",
          });
          await loadModels();
        } catch (error) {
          toast(error.message, "error");
          button.disabled = false;
        }
      }

      function installGenericRetry() {
        const current = document.querySelector("#retryJob");
        if (!current || current.dataset.genericRetry === "true") return;
        const replacement = current.cloneNode(true);
        replacement.dataset.genericRetry = "true";
        current.replaceWith(replacement);
        replacement.addEventListener("click", retryTrackedJob);

        const previousUpdateJobPanelFinal = updateJobPanel;
        updateJobPanel = function updateJobPanelWithGenericRetry(job) {
          previousUpdateJobPanelFinal(job);
          const actions = document.querySelector("#jobRecoveryActions");
          const retry = document.querySelector("#retryJob");
          if (job?.state === "failed" && actions && retry) {
            actions.hidden = false;
            retry.hidden = false;
            retry.textContent = job.error_code === "job_interrupted" ? "Retry interrupted job" : "Retry";
          }
        };
      }

      async function retryTrackedJob() {
        if (state.activeJob?.state !== "failed" || !state.activeJobProjectId) return;
        const button = document.querySelector("#retryJob");
        button.disabled = true;
        button.textContent = "Starting…";
        try {
          const job = await api(
            `/api/projects/${state.activeJobProjectId}/jobs/${state.activeJob.id}/retry`,
            { method: "POST" },
          );
          const project = await api(`/api/projects/${state.activeJobProjectId}`);
          monitorJob(job, project.id, project.name);
          toast(`Retry started for ${project.name}.`);
        } catch (error) {
          toast(error.message, "error");
          button.disabled = false;
          button.textContent = "Retry";
        }
      }

      document.addEventListener("DOMContentLoaded", () => {
        installStyles();
        installImportOptions();
        installProjectPreferenceDialog();
        installProjectPreferenceAction();
        installExportOptions();
        installModelManager();
        installGenericRetry();
        renderProjects();
      });
    })();
    ''',
)

# Cross-platform launchers.
write(
    "start-accessible-caption-studio.sh",
    r'''
    #!/usr/bin/env sh
    set -eu

    SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
    cd "$SCRIPT_DIR"

    if command -v python3 >/dev/null 2>&1; then
      BOOTSTRAP_PYTHON=$(command -v python3)
    elif command -v python >/dev/null 2>&1; then
      BOOTSTRAP_PYTHON=$(command -v python)
    else
      echo "Python 3 is required to prepare Accessible Caption Studio."
      exit 1
    fi

    if [ ! -x .bootstrap/bin/uv ]; then
      echo "Preparing the private local installer..."
      "$BOOTSTRAP_PYTHON" -m venv .bootstrap
      .bootstrap/bin/python -m pip install --upgrade pip uv
    fi

    export UV_PYTHON_INSTALL_DIR="$PWD/.runtime/python"
    export UV_CACHE_DIR="$PWD/.runtime/cache"
    export MPLCONFIGDIR="$PWD/storage/temporary/matplotlib"

    if [ ! -f .setup-complete-v5 ] || [ ! -x .studio-venv/bin/python ]; then
      echo "Preparing Accessible Caption Studio. The first setup can take several minutes."
      .bootstrap/bin/uv python install 3.11 --install-dir "$UV_PYTHON_INSTALL_DIR" --no-bin
      .bootstrap/bin/uv venv --python 3.11 --clear .studio-venv
      .bootstrap/bin/uv pip install --python .studio-venv/bin/python -e ".[ml]"
      touch .setup-complete-v5
    fi

    exec .studio-venv/bin/accessible-caption-studio start
    ''',
)
write(
    "Start Accessible Caption Studio.ps1",
    r'''
    $ErrorActionPreference = "Stop"
    Set-Location $PSScriptRoot

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Bootstrap = @("py", "-3")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $Bootstrap = @("python")
    } else {
        throw "Python 3 is required to prepare Accessible Caption Studio."
    }

    if (-not (Test-Path ".bootstrap\Scripts\python.exe")) {
        Write-Host "Preparing the private local installer..."
        & $Bootstrap[0] @($Bootstrap[1..($Bootstrap.Length - 1)] | Where-Object { $_ }) -m venv .bootstrap
        & ".bootstrap\Scripts\python.exe" -m pip install --upgrade pip uv
    }

    $env:UV_PYTHON_INSTALL_DIR = Join-Path $PWD ".runtime\python"
    $env:UV_CACHE_DIR = Join-Path $PWD ".runtime\cache"
    $env:MPLCONFIGDIR = Join-Path $PWD "storage\temporary\matplotlib"

    if (-not (Test-Path ".setup-complete-v5") -or -not (Test-Path ".studio-venv\Scripts\python.exe")) {
        Write-Host "Preparing Accessible Caption Studio. The first setup can take several minutes."
        & ".bootstrap\Scripts\python.exe" -m uv python install 3.11 --install-dir $env:UV_PYTHON_INSTALL_DIR --no-bin
        & ".bootstrap\Scripts\python.exe" -m uv venv --python 3.11 --clear .studio-venv
        & ".bootstrap\Scripts\python.exe" -m uv pip install --python ".studio-venv\Scripts\python.exe" -e ".[ml]"
        New-Item -ItemType File -Path ".setup-complete-v5" -Force | Out-Null
    }

    & ".studio-venv\Scripts\accessible-caption-studio.exe" start
    ''',
)

write(
    "docs/PLATFORM_SETUP.md",
    r'''
    # Platform setup

    Accessible Caption Studio keeps projects and model caches local. Python 3 is only needed for the first bootstrap; the launchers then create a project-local Python 3.11 runtime and environment.

    ## macOS

    Double-click `Start Accessible Caption Studio.command`, or run it from Terminal. The existing macOS launcher remains the primary path on Intel Macs.

    ## Linux

    Install FFmpeg with your distribution package manager, then run:

    ```bash
    chmod +x start-accessible-caption-studio.sh
    ./start-accessible-caption-studio.sh
    ```

    ## Windows

    Install FFmpeg and make `ffmpeg` and `ffprobe` available on PATH. From PowerShell in the repository folder run:

    ```powershell
    Set-ExecutionPolicy -Scope Process Bypass
    .\Start Accessible Caption Studio.ps1
    ```

    The Settings > System readiness section confirms FFmpeg, FFprobe, Python, disk space, and recovered jobs before long processing work.
    ''',
)

write(
    ".github/workflows/release.yml",
    r'''
    name: Release packages

    on:
      push:
        tags:
          - "v*"

    permissions:
      contents: write

    jobs:
      verify-and-package:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with:
              python-version: "3.11"
          - name: Install packaging and test dependencies
            run: |
              python -m pip install --upgrade pip build
              python -m pip install -e ".[dev]"
          - name: Lint and unit tests
            run: |
              ruff check . --ignore E501
              node --check src/accessible_caption_studio/web/app.js
              node --check src/accessible_caption_studio/web/final_batch.js
              pytest -q --ignore=tests/browser
          - name: Build Python packages
            run: python -m build
          - name: Build portable source archive and checksums
            run: |
              mkdir -p release
              git archive --format=zip --output="release/accessible-caption-studio-${GITHUB_REF_NAME}-source.zip" HEAD
              sha256sum dist/* release/* > SHA256SUMS.txt
          - name: Publish GitHub release
            env:
              GH_TOKEN: ${{ github.token }}
            run: gh release create "$GITHUB_REF_NAME" dist/* release/* SHA256SUMS.txt --generate-notes
    ''',
)

# Synthetic media/export regression corpus.
write(
    "tests/media_corpus/README.md",
    r'''
    # Generated media regression corpus

    The regression suite generates tiny local media fixtures at test time instead of checking large binary videos into Git. It covers landscape and portrait geometry, low resolution, a one-frame 4K source, MOV, WebM, audio-only WAV, non-square pixels, and long filenames. `tests/test_media_geometry.py` separately covers sample-aspect-ratio and rotation logic and performs captioned MP4 geometry exports.
    ''',
)
write(
    "tests/test_media_regression_corpus.py",
    r'''
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


    def _video(path: Path, size: str, codec: str, *, frames: int = 2) -> None:
        if codec not in _encoders():
            pytest.skip(f"FFmpeg encoder {codec} is unavailable")
        subprocess.run(
            [
                _ffmpeg(),
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c=navy:s={size}:r=2",
                "-frames:v",
                str(frames),
                "-c:v",
                codec,
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            capture_output=True,
        )


    @pytest.mark.parametrize(
        ("filename", "size", "codec", "expected"),
        [
            ("landscape.mp4", "320x180", "libx264", (320, 180)),
            ("portrait.mp4", "180x320", "libx264", (180, 320)),
            ("low-resolution.mov", "96x54", "mpeg4", (96, 54)),
            ("browser-source.webm", "160x90", "libvpx-vp9", (160, 90)),
            ("4k-single-frame.mp4", "3840x2160", "libx264", (3840, 2160)),
        ],
    )
    def test_generated_video_corpus(
        tmp_path: Path, filename: str, size: str, codec: str, expected: tuple[int, int]
    ) -> None:
        path = tmp_path / filename
        _video(path, size, codec, frames=1 if "4k" in filename else 2)
        media = inspect_media(path)
        assert media.has_video is True
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
                "sine=frequency=440:duration=.25",
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
        _video(path, "108x192", "libx264")
        media = inspect_media(path)
        assert media.has_video is True
        assert media.width == 108
        assert media.height == 192
    ''',
)

write(
    "tests/test_final_roadmap.py",
    r'''
    from pathlib import Path

    from fastapi.testclient import TestClient

    from accessible_caption_studio.captions import parse_ttml_text, to_ttml
    from accessible_caption_studio.migrations import CURRENT_PROJECT_SCHEMA_VERSION, migrate_project_payload
    from accessible_caption_studio.model_management import ModelManager
    from accessible_caption_studio.models import AnalysisJob, CaptionCue, JobState, MediaAsset, Project
    from accessible_caption_studio.reports import accessibility_report_html
    from accessible_caption_studio.webapp import create_app


    def test_ttml_round_trip_preserves_timing_and_text() -> None:
        cues = [
            CaptionCue(start=1.25, end=3.75, text="Hello there", speaker="Speaker 1"),
            CaptionCue(start=4, end=5.5, text="[music]", source="sound"),
        ]
        content = to_ttml(cues, "es")
        parsed = parse_ttml_text(content)
        assert len(parsed) == 2
        assert parsed[0].start == 1.25
        assert parsed[0].end == 3.75
        assert parsed[0].speaker == "Speaker 1"
        assert parsed[0].text == "Hello there"


    def test_schema_v2_migrates_language_and_sdh_defaults() -> None:
        payload = {"schema_version": 2, "name": "Legacy", "cues": []}
        migrated, changed = migrate_project_payload(payload)
        assert changed is True
        assert migrated["schema_version"] == CURRENT_PROJECT_SCHEMA_VERSION == 3
        assert migrated["transcription_language"] == "en"
        assert migrated["sdh_mode"] == "full"


    def test_authoring_report_contains_statistics_and_non_certification_notice() -> None:
        project = Project(name="Report project")
        project.media = MediaAsset(
            filename="video.mp4",
            stored_name="video.mp4",
            duration=10,
            width=320,
            height=180,
            has_video=True,
        )
        project.cues = [CaptionCue(start=0, end=2, text="Hello world")]
        report = accessibility_report_html(project)
        assert "Accessibility authoring report" in report
        assert "Timeline coverage" in report
        assert "not a legal certification" in report


    def _client(tmp_path: Path) -> tuple[TestClient, str]:
        app = create_app(tmp_path / "storage")
        project = app.state.store.create("Final batch")
        project.media = MediaAsset(
            filename="audio.wav", stored_name="audio.wav", duration=10, has_video=False
        )
        project.cues = [CaptionCue(start=0, end=2, text="Hello")]
        app.state.store.save(project)
        return TestClient(app), project.id


    def test_project_preferences_and_new_exports(tmp_path: Path) -> None:
        client, project_id = _client(tmp_path)
        preferences = client.patch(
            f"/api/projects/{project_id}/preferences",
            json={"transcription_language": "es", "sdh_mode": "conservative"},
        )
        assert preferences.status_code == 200
        assert preferences.json()["transcription_language"] == "es"
        assert preferences.json()["sdh_mode"] == "conservative"
        for format_name in ("ttml", "report"):
            response = client.post(f"/api/projects/{project_id}/exports/{format_name}")
            assert response.status_code == 201
            filename = response.json()["filename"]
            downloaded = client.get(f"/api/projects/{project_id}/exports/{filename}")
            assert downloaded.status_code == 200
            assert downloaded.text


    def test_overlap_retry_reuses_persisted_interval(tmp_path: Path) -> None:
        client, project_id = _client(tmp_path)
        store = client.app.state.store
        failed = AnalysisJob(
            project_id=project_id,
            kind="overlap-analysis",
            state=JobState.FAILED,
            parameters={"start": 1.0, "end": 2.0},
            error="interrupted",
        )
        store.write_job(failed)
        response = client.post(f"/api/projects/{project_id}/jobs/{failed.id}/retry")
        assert response.status_code == 202
        assert response.json()["kind"] == "overlap-analysis"
        assert response.json()["parameters"] == {"start": 1.0, "end": 2.0}


    def test_model_manager_lists_individual_components(tmp_path: Path) -> None:
        manager = ModelManager(tmp_path / "models")
        rows = manager.list()
        ids = {row["id"] for row in rows}
        assert "whisper-en-accurate" in ids
        assert "whisper-multilingual-accurate" in ids
        assert "speaker-ecapa" in ids
        assert "sound-ast" in ids
        assert "face-yunet-sface" in ids
    ''',
)

write(
    "tests/browser/test_accessibility_regressions.py",
    r'''
    import re

    import pytest
    from playwright.sync_api import Page, expect

    pytestmark = pytest.mark.browser


    def _open(page: Page, studio_url: str) -> None:
        page.goto(studio_url, wait_until="networkidle")
        expect(page).to_have_title(re.compile("Accessible Caption Studio"))


    @pytest.mark.parametrize("width", [640, 320])
    def test_zoom_equivalent_reflow_has_no_page_overflow(
        page: Page, studio_url: str, width: int
    ) -> None:
        page.set_viewport_size({"width": width, "height": 900})
        _open(page, studio_url)
        expect(page.get_by_role("button", name="Create captions")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


    def test_reduced_motion_removes_meaningful_ui_transitions(
        page: Page, studio_url: str
    ) -> None:
        page.emulate_media(reduced_motion="reduce")
        _open(page, studio_url)
        page.evaluate("toast('Reduced motion test')")
        notification = page.locator(".notification").last
        expect(notification).to_be_visible()
        seconds = notification.evaluate(
            "element => parseFloat(getComputedStyle(element).transitionDuration) || 0"
        )
        assert seconds <= 0.001


    def test_forced_colors_keeps_primary_controls_visible(page: Page, studio_url: str) -> None:
        page.emulate_media(forced_colors="active")
        _open(page, studio_url)
        expect(page.get_by_role("button", name="Settings")).to_be_visible()
        expect(page.get_by_role("button", name="Create captions")).to_be_visible()
        page.get_by_role("button", name="Settings").focus()
        expect(page.get_by_role("button", name="Settings")).to_be_focused()
    ''',
)

# Document the strengthened automated accessibility coverage.
replace(
    "docs/ACCESSIBILITY_TESTING.md",
    "- the new project search/filter/sort controls at desktop and mobile widths\n",
    "- the new project search/filter/sort controls at desktop and mobile widths\n- 320 CSS-pixel and 640 CSS-pixel reflow proxies for 400% and 200% zoom\n- reduced-motion media emulation with effectively disabled UI transitions\n- forced-colors media emulation with primary controls remaining operable\n",
)

# README cross-platform pointer and roadmap completion notes.
readme = ROOT / "README.md"
readme_text = readme.read_text(encoding="utf-8")
marker = "## Cross-platform launch and releases"
if marker not in readme_text:
    readme_text += dedent(
        r'''

        ## Cross-platform launch and releases

        macOS can continue to use `Start Accessible Caption Studio.command`. Linux users can run `start-accessible-caption-studio.sh`, and Windows users can run `Start Accessible Caption Studio.ps1`. See `docs/PLATFORM_SETUP.md` for FFmpeg and launcher details.

        Version tags matching `v*` run the release workflow, verify lint/tests, build the Python wheel and source distribution, create a portable source ZIP, generate SHA-256 checksums, and publish the files to a GitHub Release.

        The studio also supports multilingual Whisper selection, Off/Conservative/Full SDH modes, individual local model management, TTML/DFXP caption files, local Recent Project thumbnails, persistent retry inputs, and exportable accessibility authoring reports.
        '''
    )
    readme.write_text(readme_text, encoding="utf-8")

print("Final roadmap patch applied.")
