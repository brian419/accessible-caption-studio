from __future__ import annotations

import json
import mimetypes
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from .analyzer import LocalAnalyzer
from .captions import parse_caption_file
from .errors import StudioError
from .exports import export_captioned_mp4, export_text
from .jobs import JobManager
from .media import download_youtube, extract_audio, inspect_media
from .models import (
    CaptionCue,
    CaptionStyle,
    ExportArtifact,
    FusionSummary,
    JobState,
    Project,
    Severity,
    SourceType,
    SpeakerTurn,
    ValidationFinding,
    WordToken,
)
from .segmentation import segment_words_by_speaker, speaker_for_interval
from .storage import ProjectStore, safe_filename
from .validation import validate_cues
from .visual import analyze_active_speakers
from .waveform import build_waveform_envelope


class YouTubeRequest(BaseModel):
    url: str
    cookie_browser: Literal["brave", "chrome", "edge", "firefox", "safari"] | None = None
    transcription_quality: Literal["fast", "accurate"] = "accurate"


class ProjectUpdate(BaseModel):
    name: str | None = None
    cues: list[CaptionCue] | None = None
    speaker_names: dict[str, str] | None = None
    transcription_quality: Literal["fast", "accurate"] | None = None
    caption_style: CaptionStyle | None = None


class FavoriteRequest(BaseModel):
    favorite: bool


class OverlapRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)


class SpeakerReanalysisRequest(BaseModel):
    expected_speaker_count: int | None = Field(default=None, ge=1, le=8)


_FALLBACK_CAPTION_FONTS = (
    {"family": "Arial", "styles": ["Regular", "Italic", "Bold", "Bold Italic"]},
    {"family": "Helvetica", "styles": ["Regular", "Oblique", "Bold", "Bold Oblique"]},
    {"family": "Verdana", "styles": ["Regular", "Italic", "Bold", "Bold Italic"]},
    {"family": "Georgia", "styles": ["Regular", "Italic", "Bold", "Bold Italic"]},
    {"family": "Courier New", "styles": ["Regular", "Italic", "Bold", "Bold Italic"]},
)


def _font_style_sort_key(style: str) -> tuple[int, int, str]:
    normalized = style.casefold()
    if any(marker in normalized for marker in ("thin", "hairline")):
        weight = 100
    elif any(marker in normalized for marker in ("extra light", "ultra light", "extralight", "ultralight")):
        weight = 200
    elif "light" in normalized:
        weight = 300
    elif any(marker in normalized for marker in ("medium",)):
        weight = 500
    elif any(marker in normalized for marker in ("semi bold", "semibold", "demi bold", "demibold")):
        weight = 600
    elif any(marker in normalized for marker in ("black", "heavy", "extra bold", "extrabold", "ultra bold")):
        weight = 900
    elif "bold" in normalized:
        weight = 700
    else:
        weight = 400
    italic = 1 if any(marker in normalized for marker in ("italic", "oblique")) else 0
    return weight, italic, normalized


@lru_cache(maxsize=1)
def _installed_caption_fonts() -> dict[str, Any]:
    executable = shutil.which("fc-list")
    families: dict[str, set[str]] = {}
    if executable:
        try:
            result = subprocess.run(
                [executable, "--format=%{family[0]}\t%{style}\n"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    family, separator, raw_style = line.partition("\t")
                    family = " ".join(family.split()).strip()
                    style = " ".join(raw_style.split(",", 1)[0].split()).strip() or "Regular"
                    if not separator or not family or any(ord(character) < 32 for character in family):
                        continue
                    normalized_style = style.casefold().replace("-", " ")
                    if any(
                        marker in normalized_style
                        for marker in ("condensed", "expanded", "narrow", "wide", "compressed")
                    ):
                        continue
                    families.setdefault(family, set()).add(style)
        except (OSError, subprocess.SubprocessError):
            families = {}

    if families:
        fonts = [
            {
                "family": family,
                "styles": sorted(styles, key=_font_style_sort_key),
            }
            for family, styles in sorted(families.items(), key=lambda item: item[0].casefold())
        ]
        return {"fonts": fonts, "source": "fontconfig", "export_compatible": True}

    return {
        "fonts": [dict(font) for font in _FALLBACK_CAPTION_FONTS],
        "source": "fallback",
        "export_compatible": False,
    }


def create_app(storage_root: Path | None = None) -> FastAPI:
    root = (storage_root or Path("storage")).resolve()
    store = ProjectStore(root)
    jobs = JobManager(store)
    app = FastAPI(title="Accessible Caption Studio", version="1.0.0")
    app.state.store = store
    app.state.jobs = jobs

    @app.exception_handler(StudioError)
    async def studio_error_handler(_request: Any, exc: StudioError) -> Response:
        return Response(
            content=f'{{"detail":{{"code":"{exc.code}","message":{_json_string(exc.message)}}}}}',
            media_type="application/json",
            status_code=400,
        )

    @app.get("/", response_class=HTMLResponse)
    def home() -> str:
        return _asset_text("index.html")

    @app.get("/styles.css")
    def styles() -> Response:
        return Response(_asset_text("styles.css"), media_type="text/css")

    @app.get("/app.js")
    def script() -> Response:
        return Response(_asset_text("app.js"), media_type="text/javascript")

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "ffmpeg": shutil.which("ffmpeg") is not None,
            "ffprobe": shutil.which("ffprobe") is not None,
            "python_version": sys.version.split()[0],
            "free_disk_bytes": shutil.disk_usage(root).free,
            "model_cache_bytes": store.summary().models_bytes,
            "recovered_jobs": len(jobs.recovered_job_ids),
            "speaker_engine": "local-ecapa",
            "speaker_token_required": False,
            "visual_speaker_engine": "sface-ecapa-v1",
        }

    @app.get("/api/caption-fonts")
    def caption_fonts() -> dict[str, Any]:
        result = _installed_caption_fonts()
        return {
            **result,
            "count": len(result["fonts"]),
        }

    @app.get("/api/projects")
    def list_projects() -> list[Project]:
        return store.list()

    @app.post("/api/projects/restore", status_code=201)
    async def restore_project_backup(
        backup: Annotated[UploadFile, File()],
    ) -> Project:
        filename = safe_filename(backup.filename or "project.acstudio.zip", "project.acstudio.zip")
        upload_path = store.temp_dir / f"restore-upload-{uuid4().hex}-{filename}"
        try:
            await _save_upload(backup, upload_path)
            return store.restore_archive(upload_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            upload_path.unlink(missing_ok=True)

    @app.post("/api/projects/upload", status_code=202)
    async def upload_project(
        media: Annotated[UploadFile, File()],
        captions: Annotated[UploadFile | None, File()] = None,
        transcription_quality: Annotated[Literal["fast", "accurate"], Form()] = "accurate",
    ) -> dict[str, Any]:
        filename = safe_filename(media.filename or "media")
        project = store.create(Path(filename).stem)
        project.transcription_quality = transcription_quality
        project_dir = store.project_dir(project.id)
        destination = project_dir / filename
        try:
            await _save_upload(media, destination)
            project.media = inspect_media(destination)
            project.media.content_type = media.content_type
            if captions and captions.filename:
                caption_name = safe_filename(captions.filename)
                caption_path = project_dir / caption_name
                await _save_upload(captions, caption_path)
                project.cues = parse_caption_file(caption_path)
                project.findings = validate_cues(project.cues, project.media.duration)
                caption_path.unlink(missing_ok=True)
                store.save(project)
                return {"project": project, "job": None}
            store.save(project)
            job = _start_analysis(project.id, store, jobs)
            return {"project": store.get(project.id), "job": job}
        except Exception:
            store.delete(project.id)
            raise

    @app.post("/api/projects/youtube", status_code=202)
    def youtube_project(request: YouTubeRequest) -> dict[str, Any]:
        project = store.create("YouTube video")
        project.transcription_quality = request.transcription_quality
        store.save(project)

        def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
            progress("Downloading", 5, "Downloading the selected YouTube video")
            project_dir = store.project_dir(project.id)
            source, title = download_youtube(
                request.url,
                project_dir,
                progress,
                cookie_browser=request.cookie_browser,
            )
            final_name = safe_filename(f"{title}{source.suffix}")
            final_path = project_dir / final_name
            source.replace(final_path)
            current = store.get(project.id)
            current.name = title
            current.media = inspect_media(final_path, source_url=request.url)
            current.media.stored_name = final_name
            store.save(current)
            _analysis_task(project.id, store, progress)

        job = jobs.start(project.id, "youtube-analysis", target)
        project.latest_job_id = job.id
        store.save(project)
        return {"project": project, "job": job}

    @app.post("/api/projects/{project_id}/favorite")
    def favorite_project(project_id: str, request: FavoriteRequest) -> Project:
        project = _get_project(store, project_id)
        project.is_favorite = request.favorite
        return store.save(project, touch=False)

    @app.get("/api/projects/{project_id}/backup")
    def backup_project(project_id: str) -> FileResponse:
        project = _get_project(store, project_id)
        archive_path = store.create_archive(project_id)
        filename = f"{safe_filename(project.name, 'Accessible Caption Studio project')} - backup.acstudio.zip"
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=filename,
            background=BackgroundTask(archive_path.unlink, missing_ok=True),
        )

    @app.get("/api/projects/{project_id}/revisions")
    def project_revisions(project_id: str) -> list[dict[str, object]]:
        _get_project(store, project_id)
        return store.list_revisions(project_id)

    @app.post("/api/projects/{project_id}/revisions/{revision_id}/restore")
    def restore_project_revision(project_id: str, revision_id: str) -> Project:
        _get_project(store, project_id)
        try:
            return store.restore_revision(project_id, revision_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Restore point not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/projects/{project_id}/waveform")
    def project_waveform(project_id: str) -> dict[str, Any]:
        project = _get_project(store, project_id)
        if not project.media:
            raise HTTPException(status_code=400, detail="Project media is not ready yet")
        project_dir = store.project_dir(project_id)
        audio_path = project_dir / "analysis.wav"
        if not audio_path.is_file():
            source = project_dir / project.media.stored_name
            extract_audio(source, audio_path)
        try:
            return build_waveform_envelope(audio_path, project_dir / "waveform.json")
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="The waveform could not be prepared for this project") from exc

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> Project:
        return _get_project(store, project_id)

    @app.patch("/api/projects/{project_id}")
    def update_project(project_id: str, request: ProjectUpdate) -> Project:
        project = _get_project(store, project_id)
        changed = (
            (request.name is not None and request.name != project.name)
            or (request.cues is not None and request.cues != project.cues)
            or (request.speaker_names is not None and request.speaker_names != project.speaker_names)
            or (
                request.transcription_quality is not None
                and request.transcription_quality != project.transcription_quality
            )
            or (request.caption_style is not None and request.caption_style != project.caption_style)
        )
        if changed:
            store.create_revision(project)
        if request.name is not None:
            project.name = request.name
        if request.cues is not None:
            project.cues = request.cues
            project.findings = validate_cues(
                project.cues, project.media.duration if project.media else None
            )
        if request.speaker_names is not None:
            project.speaker_names = request.speaker_names
        if request.transcription_quality is not None:
            project.transcription_quality = request.transcription_quality
        if request.caption_style is not None:
            project.caption_style = request.caption_style
        return store.save(project)

    @app.delete("/api/projects/{project_id}", status_code=204)
    def delete_project(project_id: str) -> Response:
        try:
            store.delete(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        return Response(status_code=204)

    @app.post("/api/projects/{project_id}/duplicate", status_code=201)
    def duplicate_project(project_id: str) -> Project:
        try:
            return store.duplicate(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc

    @app.post("/api/projects/{project_id}/analyze", status_code=202)
    def analyze_project(project_id: str) -> Any:
        _get_project(store, project_id)
        return _start_analysis(project_id, store, jobs)

    @app.post("/api/projects/{project_id}/analyze-overlap", status_code=202)
    def analyze_overlap(project_id: str, request: OverlapRequest) -> Any:
        project = _get_project(store, project_id)
        if not project.media:
            raise HTTPException(status_code=400, detail="Media is not ready for analysis")
        if request.end <= request.start:
            raise HTTPException(status_code=400, detail="End time must follow start time")

        def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
            project_dir = store.project_dir(project_id)
            audio = project_dir / "analysis.wav"
            if not audio.is_file():
                extract_audio(project_dir / project.media.stored_name, audio)
            analyzer = LocalAnalyzer(project_dir, model_cache_dir=store.models_dir)
            progress("Inspecting overlap", 5, "Separating overlapping voices")
            proposal = analyzer.overlap_proposal(
                audio,
                request.start,
                request.end,
                project.speakers,
                project.cues,
                progress=progress,
            )
            result_path = project_dir / f"overlap-{_job.id}.json"
            result_path.write_text(json.dumps(proposal, default=_json_default), encoding="utf-8")

        return jobs.start(project_id, "overlap", target)

    @app.get("/api/projects/{project_id}/overlap-proposals/{job_id}")
    def overlap_proposal(project_id: str, job_id: str) -> Any:
        _get_project(store, project_id)
        path = store.project_dir(project_id) / f"overlap-{safe_filename(job_id)}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Overlap proposal not ready")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.post("/api/projects/{project_id}/reanalyze-speakers", status_code=202)
    def reanalyze_speakers(project_id: str, request: SpeakerReanalysisRequest) -> AnalysisJob:
        project = _get_project(store, project_id)
        if not project.media:
            raise HTTPException(status_code=400, detail="Media is not ready for speaker analysis")
        if not project.words:
            raise HTTPException(
                status_code=400,
                detail="Run automatic caption analysis before re-detecting speakers",
            )
        project.expected_speaker_count = request.expected_speaker_count
        store.save(project)

        def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
            project_dir = store.project_dir(project_id)
            audio = project_dir / "analysis.wav"
            if not audio.is_file():
                extract_audio(project_dir / project.media.stored_name, audio)
            turns, face_tracks, fusion = analyze_active_speakers(
                project_dir / project.media.stored_name,
                audio,
                project.words,
                project_dir,
                store.models_dir,
                progress=progress,
                expected_speaker_count=request.expected_speaker_count,
            )
            result = segment_words_by_speaker(project.words, turns, project.cues)
            payload = {
                "detected_count": fusion.final_speaker_count,
                "turns": [turn.model_dump(mode="json") for turn in turns],
                "face_tracks": [track.model_dump(mode="json") for track in face_tracks],
                "fusion_summary": fusion.model_dump(mode="json"),
                "cues": [cue.model_dump(mode="json") for cue in result.cues],
                "change_summary": result.change_summary,
                "name_review_warnings": result.name_review_warnings,
            }
            result_path = project_dir / f"speaker-proposal-{_job.id}.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

        return jobs.start(project_id, "speaker-reanalysis", target)

    @app.get("/api/projects/{project_id}/speaker-proposals/{job_id}")
    def speaker_proposal(project_id: str, job_id: str) -> Any:
        _get_project(store, project_id)
        path = store.project_dir(project_id) / f"speaker-proposal-{safe_filename(job_id)}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Speaker proposal not ready")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.post("/api/projects/{project_id}/speaker-proposals/{job_id}/apply")
    def apply_speaker_proposal(project_id: str, job_id: str) -> Project:
        project = _get_project(store, project_id)
        path = store.project_dir(project_id) / f"speaker-proposal-{safe_filename(job_id)}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Speaker proposal not ready")
        payload = json.loads(path.read_text(encoding="utf-8"))
        previous_names = dict(project.speaker_names)
        project.speakers = [SpeakerTurn.model_validate(item) for item in payload["turns"]]
        project.face_tracks = [
            _face_track_from_payload(item) for item in payload.get("face_tracks", [])
        ]
        project.fusion_summary = FusionSummary.model_validate(payload.get("fusion_summary", {}))
        project.cues = [CaptionCue.model_validate(item) for item in payload["cues"]]
        project.expected_speaker_count = project.fusion_summary.final_speaker_count or None
        project.speaker_engine = "ecapa_sface_v1"
        project.visual_speaker_status = "complete"
        project.speaker_names = {
            speaker: display
            for speaker, display in previous_names.items()
            if any(cue.speaker == speaker for cue in project.cues)
        }
        project.findings = validate_cues(project.cues, project.media.duration if project.media else None)
        store.save(project)
        path.unlink(missing_ok=True)
        return project

    @app.post("/api/projects/{project_id}/repair-transcript", status_code=202)
    def repair_transcript(project_id: str) -> AnalysisJob:
        project = _get_project(store, project_id)
        if not project.media:
            raise HTTPException(status_code=400, detail="Media is not ready for transcript repair")
        if not project.words:
            raise HTTPException(
                status_code=400,
                detail="Run automatic caption analysis before improving the transcript",
            )

        def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
            project_dir = store.project_dir(project_id)
            audio = project_dir / "analysis.wav"
            if not audio.is_file():
                extract_audio(project_dir / project.media.stored_name, audio)
            analyzer = LocalAnalyzer(project_dir, model_cache_dir=store.models_dir)
            progress("Checking transcript", 5, "Finding speech regions that need a second pass")
            proposal = analyzer.transcript_repair_proposal(
                audio,
                project.words,
                project.cues,
                project.speakers,
                progress=progress,
            )
            payload = {
                "words": [word.model_dump(mode="json") for word in proposal.words],
                "cues": [cue.model_dump(mode="json") for cue in proposal.cues],
                "recovery_summary": proposal.recovery_summary,
                "edit_conflicts": proposal.edit_conflicts,
            }
            result_path = project_dir / f"transcript-proposal-{_job.id}.json"
            result_path.write_text(json.dumps(payload), encoding="utf-8")

        return jobs.start(project_id, "transcript-repair", target)

    @app.get("/api/projects/{project_id}/transcript-proposals/{job_id}")
    def transcript_proposal(project_id: str, job_id: str) -> Any:
        _get_project(store, project_id)
        path = store.project_dir(project_id) / f"transcript-proposal-{safe_filename(job_id)}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Transcript proposal not ready")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.post("/api/projects/{project_id}/transcript-proposals/{job_id}/apply")
    def apply_transcript_proposal(project_id: str, job_id: str) -> Project:
        project = _get_project(store, project_id)
        path = store.project_dir(project_id) / f"transcript-proposal-{safe_filename(job_id)}.json"
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Transcript proposal not ready")
        payload = json.loads(path.read_text(encoding="utf-8"))
        project.words = [WordToken.model_validate(item) for item in payload["words"]]
        project.cues = [CaptionCue.model_validate(item) for item in payload["cues"]]
        project.findings = validate_cues(project.cues, project.media.duration if project.media else None)
        store.save(project)
        path.unlink(missing_ok=True)
        return project

    @app.post("/api/projects/{project_id}/validate")
    def validate_project(project_id: str) -> Project:
        project = _get_project(store, project_id)
        project.findings = validate_cues(project.cues, project.media.duration if project.media else None)
        return store.save(project)

    @app.get("/api/projects/{project_id}/media")
    def media_file(project_id: str) -> FileResponse:
        project = _get_project(store, project_id)
        if not project.media:
            raise HTTPException(status_code=404, detail="Project has no media yet")
        return FileResponse(
            store.project_dir(project_id) / project.media.stored_name,
            media_type=project.media.content_type or mimetypes.guess_type(project.media.filename)[0],
        )

    @app.get("/api/projects/{project_id}/jobs/{job_id}")
    def get_job(project_id: str, job_id: str) -> AnalysisJob:
        try:
            job = jobs.get(project_id, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        return job

    @app.post("/api/projects/{project_id}/jobs/{job_id}/cancel", status_code=202)
    def cancel_job(project_id: str, job_id: str) -> AnalysisJob:
        try:
            return jobs.cancel(project_id, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.get("/api/projects/{project_id}/exports/{filename}")
    def get_export(project_id: str, filename: str) -> FileResponse:
        project = _get_project(store, project_id)
        artifact = next((item for item in project.exports if item.filename == filename), None)
        if not artifact:
            raise HTTPException(status_code=404, detail="Export not found")
        return FileResponse(store.project_dir(project_id) / "exports" / artifact.filename)

    @app.post("/api/projects/{project_id}/exports/{format_name}", status_code=201)
    def create_export(project_id: str, format_name: str) -> Any:
        project = _get_project(store, project_id)
        if format_name == "mp4":
            if not project.media or not project.media.has_video:
                raise HTTPException(status_code=400, detail="MP4 export needs video")
            return _start_mp4_export(project_id, store, jobs)
        try:
            artifact = export_text(project, store.project_dir(project_id), format_name)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Unsupported export format") from exc
        project.exports.append(artifact)
        return store.save(project)

    @app.get("/api/storage")
    def storage_summary() -> Any:
        return store.summary()

    @app.delete("/api/storage/{target}", status_code=204)
    def clear_storage(target: str) -> Response:
        try:
            store.clear_cache(target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    return app


def _analysis_task(
    project_id: str,
    store: ProjectStore,
    progress: Callable[[str, int, str], None],
    _job_context: Any | None = None,
) -> None:
    project = store.get(project_id)
    if not project.media:
        raise StudioError("missing_media", "Project media is not ready.")
    project_dir = store.project_dir(project.id)
    audio = project_dir / "analysis.wav"
    progress("Preparing audio", 5, "Extracting a private local audio track")
    extract_audio(project_dir / project.media.stored_name, audio, _job_context)
    analyzer = LocalAnalyzer(project_dir, model_cache_dir=store.models_dir)
    progress("Analyzing", 10, "Running local speech, speaker, face, and sound models")
    project = analyzer.analyze(project, audio, progress, _job_context)
    project.findings = validate_cues(project.cues, project.media.duration)
    store.save(project)


def _start_analysis(project_id: str, store: ProjectStore, jobs: JobManager) -> AnalysisJob:
    job = jobs.start(
        project_id,
        "analysis",
        lambda _job, progress: _analysis_task(project_id, store, progress, _job),
    )
    project = store.get(project_id)
    project.latest_job_id = job.id
    store.save(project)
    return job


def _start_mp4_export(project_id: str, store: ProjectStore, jobs: JobManager) -> AnalysisJob:
    def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
        project = store.get(project_id)
        duration = max(project.media.duration if project.media else 0, 0.001)

        def render_progress(percent: int, _elapsed: float) -> None:
            progress(
                "Rendering video",
                max(1, min(99, percent)),
                f"Rendering captioned video · {percent}%",
            )

        progress("Preparing video", 1, "Preparing caption style and video frames")
        artifact = export_captioned_mp4(
            project,
            store.project_dir(project_id),
            render_progress,
            _job,
        )
        current = store.get(project_id)
        current.exports.append(artifact)
        store.save(current)
        progress("Complete", 100, f"Rendered {duration:.1f} seconds of video")

    job = jobs.start(project_id, "mp4-export", target)
    project = store.get(project_id)
    project.latest_job_id = job.id
    store.save(project)
    return job


def _face_track_from_payload(item: dict[str, Any]) -> Any:
    from .models import FaceTrackSummary

    return FaceTrackSummary.model_validate(item)


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError


def _asset_text(name: str) -> str:
    return files("accessible_caption_studio.web").joinpath(name).read_text(encoding="utf-8")


def _get_project(store: ProjectStore, project_id: str) -> Project:
    try:
        return store.get(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


def _json_string(value: str) -> str:
    return json.dumps(value)


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".partial")
    with temporary.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            handle.write(chunk)
    temporary.replace(destination)
