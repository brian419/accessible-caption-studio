from __future__ import annotations

import mimetypes
import shutil
from collections.abc import Callable
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from .analyzer import LocalAnalyzer
from .captions import parse_caption_file
from .errors import StudioError
from .exports import export_captioned_mp4, export_text
from .jobs import JobManager
from .media import download_youtube, extract_audio, inspect_media
from .models import CaptionCue, ExportArtifact, Project, Severity, ValidationFinding
from .storage import ProjectStore, safe_filename
from .validation import validate_cues


class YouTubeRequest(BaseModel):
    url: str


class ProjectUpdate(BaseModel):
    name: str | None = None
    cues: list[CaptionCue] | None = None


class TokenRequest(BaseModel):
    token: str


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
            "hf_token_configured": bool(store.settings().get("hf_token")),
        }

    @app.get("/api/projects")
    def list_projects() -> list[Project]:
        return store.list()

    @app.post("/api/projects/upload", status_code=202)
    async def upload_project(
        media: Annotated[UploadFile, File()],
        captions: Annotated[UploadFile | None, File()] = None,
    ) -> dict[str, Any]:
        filename = safe_filename(media.filename or "media")
        project = store.create(Path(filename).stem)
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

        def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
            progress("Downloading", 5, "Downloading the selected YouTube video")
            project_dir = store.project_dir(project.id)
            source, title = download_youtube(request.url, project_dir)
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

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> Project:
        return _get_project(store, project_id)

    @app.patch("/api/projects/{project_id}")
    def update_project(project_id: str, request: ProjectUpdate) -> Project:
        project = _get_project(store, project_id)
        if request.name is not None:
            project.name = request.name
        if request.cues is not None:
            project.cues = request.cues
            project.findings = validate_cues(
                project.cues, project.media.duration if project.media else None
            )
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

    @app.post("/api/projects/{project_id}/validate")
    def validate_project(project_id: str) -> Project:
        project = _get_project(store, project_id)
        project.findings = validate_cues(
            project.cues, project.media.duration if project.media else None
        )
        return store.save(project)

    @app.get("/api/projects/{project_id}/media")
    def project_media(project_id: str) -> FileResponse:
        project = _get_project(store, project_id)
        if not project.media:
            raise HTTPException(status_code=404, detail="Media is not ready")
        path = store.project_dir(project_id) / project.media.stored_name
        return FileResponse(
            path, media_type=project.media.content_type or mimetypes.guess_type(path)[0]
        )

    @app.get("/api/projects/{project_id}/jobs/{job_id}")
    def get_job(project_id: str, job_id: str) -> Any:
        try:
            return jobs.get(project_id, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/api/projects/{project_id}/jobs/{job_id}/cancel")
    def cancel_job(project_id: str, job_id: str) -> Any:
        try:
            return jobs.cancel(project_id, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.post("/api/projects/{project_id}/exports/{format_name}", status_code=201)
    def create_export(project_id: str, format_name: str) -> ExportArtifact | Any:
        project = _get_project(store, project_id)
        if not project.cues:
            raise HTTPException(status_code=400, detail="Add captions before exporting")
        if format_name in {"srt", "vtt", "html"}:
            artifact = export_text(project, store.project_dir(project_id), format_name)
            project.exports = [item for item in project.exports if item.format != format_name]
            project.exports.append(artifact)
            store.save(project)
            return artifact
        if format_name != "mp4":
            raise HTTPException(status_code=400, detail="Unsupported export format")

        def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
            progress("Preparing video", 5, "Starting the captioned-video renderer")
            current = store.get(project_id)

            def render_progress(percent: int, elapsed: float) -> None:
                total = current.media.duration if current.media else 0
                job_percent = min(97, max(2, percent))
                progress(
                    "Rendering captioned video",
                    job_percent,
                    f"{percent}% encoded · {_clock(elapsed)} of {_clock(total)}",
                )

            artifact = export_captioned_mp4(
                current,
                store.project_dir(project_id),
                progress=render_progress,
            )
            current.exports = [item for item in current.exports if item.format != "mp4"]
            current.exports.append(artifact)
            store.save(current)
            progress("Finalizing", 99, "Saving the finished captioned video")

        job = jobs.start(project_id, "mp4-export", target)
        project.latest_job_id = job.id
        store.save(project)
        return job

    @app.get("/api/projects/{project_id}/exports/{filename}")
    def download_export(project_id: str, filename: str) -> FileResponse:
        project = _get_project(store, project_id)
        safe = safe_filename(filename)
        if not any(item.filename == safe for item in project.exports):
            raise HTTPException(status_code=404, detail="Export not found")
        path = store.project_dir(project_id) / "exports" / safe
        return FileResponse(path, filename=safe)

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

    @app.post("/api/settings/hugging-face-token", status_code=204)
    def save_token(request: TokenRequest) -> Response:
        try:
            store.save_hf_token(request.token)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    return app


def _start_analysis(project_id: str, store: ProjectStore, jobs: JobManager) -> Any:
    def target(_job: Any, progress: Callable[[str, int, str], None]) -> None:
        _analysis_task(project_id, store, progress)

    job = jobs.start(project_id, "analysis", target)
    project = store.get(project_id)
    project.latest_job_id = job.id
    store.save(project)
    return job


def _analysis_task(
    project_id: str,
    store: ProjectStore,
    progress: Callable[[str, int, str], None],
) -> None:
    project = store.get(project_id)
    if not project.media:
        raise StudioError("media_not_ready", "Media is not ready for analysis.")
    project_dir = store.project_dir(project_id)
    source = project_dir / project.media.stored_name
    audio = project_dir / "analysis.wav"
    progress("Preparing audio", 10, "Extracting a private local analysis track")
    if not audio.is_file():
        extract_audio(source, audio)
    analyzer = LocalAnalyzer(store.models_dir, store.settings().get("hf_token"))
    words, speakers, sounds, cues = analyzer.analyze(audio, progress)
    project = store.get(project_id)
    project.words = words
    project.speakers = speakers
    project.sounds = sounds
    project.cues = cues
    project.findings = validate_cues(cues, project.media.duration)
    project.findings.extend(
        ValidationFinding(
            code=code,
            message=f"Optional automatic feature skipped: {message}",
            severity=Severity.WARNING,
        )
        for code, message in analyzer.warnings
    )
    store.save(project)
    progress("Saving", 95, "Saving captions and accessibility findings")


async def _save_upload(upload: UploadFile, destination: Path) -> None:
    partial = destination.with_suffix(destination.suffix + ".partial")
    try:
        with partial.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                handle.write(chunk)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
        await upload.close()


def _get_project(store: ProjectStore, project_id: str) -> Project:
    try:
        return store.get(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Project not found") from exc


def _asset_text(name: str) -> str:
    return files("accessible_caption_studio").joinpath("web", name).read_text(encoding="utf-8")


def _json_string(value: str) -> str:
    import json

    return json.dumps(value)


def _clock(seconds: float) -> str:
    seconds = max(0, round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


app = create_app()
