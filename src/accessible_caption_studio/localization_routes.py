from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .errors import StudioError
from .jobs import JobManager
from .localization import create_translation_track, normalize_target_languages
from .models import AnalysisJob, Project
from .storage import ProjectStore


class CaptionTranslationRequest(BaseModel):
    target_languages: list[str] = Field(default_factory=list)
    replace_existing: bool = False


class CaptionTrackReviewRequest(BaseModel):
    review_state: Literal["unreviewed", "in_review", "reviewed"]


def start_translation_job(
    project_id: str,
    store: ProjectStore,
    jobs: JobManager,
    target_languages: list[str],
    *,
    replace_existing: bool = False,
) -> AnalysisJob:
    targets = normalize_target_languages(target_languages)
    if not targets:
        raise ValueError("Choose at least one caption language to translate")
    project = store.get(project_id)
    if not project.original_caption_track().cues:
        raise ValueError("Create or import original captions before translating")

    def target(job: Any, progress: Any) -> None:
        current = store.get(project_id)
        created: list[dict[str, str]] = []
        for index, language in enumerate(targets):
            progress(
                "Preparing translation",
                max(5, round(index / max(1, len(targets)) * 80)),
                f"Preparing {language} caption track",
            )
            track = create_translation_track(
                current,
                language,
                store.models_dir,
                progress,
                replace_existing=replace_existing,
            )
            created.append({"id": track.id, "language": track.language})
            store.save(current)
        job.result = {"type": "caption_translation", "tracks": created}
        progress("Translation ready", 98, "Translated caption tracks are ready for review")

    job = jobs.start(
        project_id,
        "caption-translation",
        target,
        parameters={
            "target_languages": targets,
            "replace_existing": replace_existing,
        },
    )
    project.latest_job_id = job.id
    store.save(project)
    return job


def register_localization_routes(
    app: FastAPI,
    store: ProjectStore,
    jobs: JobManager,
) -> None:
    @app.get("/api/projects/{project_id}/caption-tracks")
    def list_caption_tracks(project_id: str) -> list[dict[str, object]]:
        try:
            project = store.get(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        return [track.model_dump(mode="json") for track in project.caption_tracks]

    @app.post("/api/projects/{project_id}/caption-tracks/translations", status_code=202)
    def translate_caption_tracks(
        project_id: str, request: CaptionTranslationRequest
    ) -> AnalysisJob:
        try:
            return start_translation_job(
                project_id,
                store,
                jobs,
                request.target_languages,
                replace_existing=request.replace_existing,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Project not found") from exc
        except (ValueError, StudioError) as exc:
            message = exc.message if isinstance(exc, StudioError) else str(exc)
            raise HTTPException(status_code=400, detail=message) from exc

    @app.post("/api/projects/{project_id}/caption-tracks/{track_id}/activate")
    def activate_caption_track(project_id: str, track_id: str) -> Project:
        try:
            project = store.get(project_id)
            project.activate_caption_track(track_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Caption track not found") from exc
        return store.save(project, touch=False)

    @app.patch("/api/projects/{project_id}/caption-tracks/{track_id}")
    def update_caption_track(
        project_id: str,
        track_id: str,
        request: CaptionTrackReviewRequest,
    ) -> Project:
        try:
            project = store.get(project_id)
            track = project.caption_track(track_id)
            if track is None:
                raise KeyError(track_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Caption track not found") from exc
        track.review_state = request.review_state
        if track.id == project.active_caption_track_id:
            project.refresh_caption_track_view()
        return store.save(project)

    @app.delete(
        "/api/projects/{project_id}/caption-tracks/{track_id}",
        status_code=204,
    )
    def delete_caption_track(project_id: str, track_id: str) -> Response:
        try:
            project = store.get(project_id)
            track = project.caption_track(track_id)
            if track is None:
                raise KeyError(track_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Caption track not found") from exc
        if track.kind == "original":
            raise HTTPException(status_code=400, detail="The original caption track cannot be deleted")
        project.sync_active_caption_track()
        project.caption_tracks = [item for item in project.caption_tracks if item.id != track_id]
        if project.active_caption_track_id == track_id:
            project.active_caption_track_id = project.original_caption_track().id
        project.refresh_caption_track_view()
        store.save(project)
        return Response(status_code=204)
