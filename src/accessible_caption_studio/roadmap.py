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
            project.spoken_language = request.transcription_language
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
                current.spoken_language = current.transcription_language
                requested = parameters.get("target_caption_languages") or []
                if isinstance(requested, list):
                    current.requested_caption_languages = [str(item) for item in requested]
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
