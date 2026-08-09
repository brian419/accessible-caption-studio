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

from .captions import parse_caption_file
from .enhanced_analyzer import LocalAnalyzer
from .errors import StudioError
from .exports import export_captioned_mp4, export_text
from .jobs import JobManager
from .localization import create_translation_track, normalize_target_languages
from .localization_routes import register_localization_routes, start_translation_job
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
from .roadmap import register_roadmap_routes
from .segmentation import segment_words_by_speaker, speaker_for_interval
from .storage import ProjectStore, safe_filename
from .validation import validate_cues
from .visual import analyze_active_speakers
from .waveform import build_waveform_envelope


class YouTubeRequest(BaseModel):
    url: str
    cookie_browser: Literal["brave", "chrome", "edge", "firefox", "safari"] | None = None
    transcription_quality: Literal["fast", "accurate"] = "accurate"
    transcription_language: str = Field(
        default="en", pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"
    )
    sdh_mode: Literal["off", "conservative", "full"] = "full"
    target_caption_languages: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: str | None = None
    cues: list[CaptionCue] | None = None
    speaker_names: dict[str, str] | None = None
    transcription_quality: Literal["fast", "accurate"] | None = None
    transcription_language: str | None = Field(
        default=None, pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$"
    )
    sdh_mode: Literal["off", "conservative", "full"] | None = None
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

    @app.get("/final-batch.js")
    def final_batch_script() -> Response:
        return Response(_asset_text("final_batch.js"), media_type="text/javascript")

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
        filename = safe_filename(
            backup.filename or "project.acstudio.zip",
            "project.acstudio.zip",
        )
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
        transcription_language: Annotated[
            str, Form(pattern=r"^(auto|[a-z]{2,3}(?:-[A-Z]{2})?)$")
        ] = "en",
        sdh_mode: Annotated[Literal["off", "conservative", "full"], Form()] = "full",
        target_caption_languages: Annotated[str, Form()] = "[]",
    ) -> dict[str, Any]:
        filename = safe_filename(media.filename or "media")
        targets = _parse_target_caption_languages(target_caption_languages)
        project = store.create(Path(filename).stem)
        project.transcription_quality = transcription_quality
        project.transcription_language = transcription_language
        project.spoken_language = transcription_language
        project.requested_caption_languages = targets
        project.sdh_mode = sdh_mode
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
                original = project.original_caption_track()
                original.language = (
                    transcription_language if transcription_language != "auto" else "und"
                )
                caption_path.unlink(missing_ok=True)
                store.save(project)
                job = (
                    start_translation_job(project.id, store, jobs, targets)
                    if targets
                    else None
                )
                return {"project": store.get(project.id), "job": job}
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
        project.transcription_language = request.transcription_language
        project.spoken_language = request.transcription_language
        project.requested_caption_languages = normalize_target_languages(
            request.target_caption_languages
        )
        project.sdh_mode = request.sdh_mode
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

        job = jobs.start(
            project.id,
            "youtube-analysis",
            target,
            parameters={
                "url": request.url,
                "cookie_browser": request.cookie_browser,
                "transcription_quality": request.transcription_quality,
                "transcription_language": request.transcription_language,
                "target_caption_languages": project.requested_caption_languages,
                "sdh_mode": request.sdh_mode,
            },
        )
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
        filename = (
            f"{safe_filename(project.name, 'Accessible Caption Studio project')}"
            " - backup.acstudio.zip"
        )
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
            raise HTTPException(
                status_code=400,
                detail="The waveform could not be prepared for this project",
            ) from exc

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> Project:
        return _get_project(store, project_id)

    @app.patch("/api/projects/{project_id}")
    def update_project(project_id: str, request: ProjectUpdate) -> Project:
        project = _get_project(store, project_id)
        changed = (
            (request.name is not None and request.name != project.name)
            or (request.cues is not None and request.cues != project.cues)
            or (
                request.speaker_names is not None
                and request.speaker_names != project.speaker_names
            )
            or (
                request.transcription_quality is not None
                and request.transcription_quality != project.transcription_quality
            )
            or (
                request.transcription_language is not None
                and request.transcription_language != project.transcription_language
            )
            or (request.sdh_mode is not None and request.sdh_mode != project.sdh_mode)
            or (
                request.caption_style is not None
                and request.caption_style != project.caption_style
            )
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
        if request.transcription_language is not None:
            project.transcription_language = request.transcription_language
            project.spoken_language = request.transcription_language
        if request.sdh_mode is not None:
            project.sdh_mode = request.sdh_mode
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
        _require_original_caption_track(project)
        if not project.media:
            raise HTTPException(status_code=400, detail="Media is not ready for analysis")
        if request.end <= request.start:
            raise HTTPException(status_code=400, detail="End time must follow start time")
        if request.end - request.start > 30:
            raise HTTPException(
                status_code=400, detail="Overlapping-voice analysis is limited to 30 seconds"
            )
        if request.end > project.media.duration + 0.05:
            raise HTTPException(status_code=400, detail="The selected interval exceeds the media")

        def target(job: Any, progress: Callable[[str, int, str], None]) -> None:
            current = store.get(project_id)
            project_dir = store.project_dir(project_id)
            audio = project_dir / "analysis.wav"
            if not audio.is_file():
                progress("Preparing audio", 5, "Extracting the selected local audio track")
                extract_audio(project_dir / current.media.stored_name, audio, progress)
            analyzer = LocalAnalyzer(
                store.models_dir,
                current.transcription_quality,
                current.transcription_language,
                current.sdh_mode,
            )
            channels, matched_speakers = analyzer.analyze_overlap(
                audio, request.start, request.end, current.speakers, progress
            )
            existing_speakers: list[str] = []
            for turn in current.speakers:
                if turn.end <= request.start or turn.start >= request.end:
                    continue
                if turn.speaker not in existing_speakers:
                    existing_speakers.append(turn.speaker)
            all_speakers = {turn.speaker for turn in current.speakers}
            next_number = 1
            while f"Speaker {next_number}" in all_speakers or len(existing_speakers) < 2:
                candidate = f"Speaker {next_number}"
                if candidate not in existing_speakers:
                    existing_speakers.append(candidate)
                next_number += 1
                if len(existing_speakers) >= 2:
                    break
            group_id = uuid4().hex
            proposals = []
            assigned_speakers: list[str] = []
            for index, words in enumerate(channels[:2]):
                confidences = [word.confidence for word in words if word.confidence is not None]
                speaker = matched_speakers[index]
                if not speaker or speaker in assigned_speakers:
                    speaker = next(
                        item for item in existing_speakers if item not in assigned_speakers
                    )
                assigned_speakers.append(speaker)
                proposals.append(
                    CaptionCue(
                        start=request.start,
                        end=request.end,
                        text=" ".join(word.text.strip() for word in words),
                        speaker=speaker,
                        source="transcription",
                        confidence=sum(confidences) / len(confidences) if confidences else None,
                        overlap_group_id=group_id,
                    ).model_dump(mode="json")
                )
            job.result = {
                "type": "overlap_proposal",
                "start": request.start,
                "end": request.end,
                "replace_cue_ids": [
                    cue.id
                    for cue in current.cues
                    if cue.start < request.end and cue.end > request.start
                ],
                "cues": proposals,
            }
            progress("Review separated voices", 95, "Two proposed speaker lines are ready")

        job = jobs.start(
            project_id,
            "overlap-analysis",
            target,
            parameters={"start": request.start, "end": request.end},
        )
        project.latest_job_id = job.id
        store.save(project)
        return job

    @app.post("/api/projects/{project_id}/reanalyze-speakers", status_code=202)
    def reanalyze_speakers(project_id: str, request: SpeakerReanalysisRequest) -> Any:
        project = _get_project(store, project_id)
        _require_original_caption_track(project)
        if not project.media or not project.words:
            raise HTTPException(
                status_code=400,
                detail="Run automatic caption analysis before re-detecting speakers",
            )
        base_updated_at = project.updated_at.isoformat()

        def target(job: Any, progress: Callable[[str, int, str], None]) -> None:
            current = store.get(project_id)
            project_dir = store.project_dir(project_id)
            audio = project_dir / "analysis.wav"
            if not audio.is_file():
                progress("Preparing audio", 5, "Extracting the local speaker-analysis track")
                extract_audio(project_dir / current.media.stored_name, audio, progress)
            progress(
                "Re-detecting speakers",
                10,
                "Loading the local voice model; this can take a few minutes on Intel Macs",
            )
            analyzer = LocalAnalyzer(
                store.models_dir,
                current.transcription_quality,
                current.transcription_language,
                current.sdh_mode,
            )
            try:
                speakers = analyzer.diarize(
                    audio,
                    current.words,
                    progress,
                    request.expected_speaker_count,
                )
                if speakers and not getattr(analyzer, "voice_cluster_count", 0):
                    analyzer.voice_cluster_count = len(
                        {turn.speaker for turn in speakers}
                    )
            except StudioError as exc:
                speakers = []
                analyzer.voice_cluster_count = 0
                analyzer.warnings.append((exc.code, exc.message))
                progress(
                    "Voice comparison unavailable",
                    65,
                    "Trying anonymous recurring-face evidence instead",
                )
            face_tracks = current.face_tracks
            visual_status = current.visual_speaker_status
            fusion_summary = FusionSummary(
                voice_cluster_count=getattr(analyzer, "voice_cluster_count", 0),
                final_speaker_count=len({turn.speaker for turn in speakers}),
            )
            evidence_temp = project_dir / f"speaker-evidence-{job.id}.json"
            visual_input = speakers or _provisional_speech_turns(current.words)
            if current.media.has_video and visual_input:
                try:
                    speakers, face_tracks, visual_status, fusion_summary = (
                        analyze_active_speakers(
                            project_dir / current.media.stored_name,
                            audio,
                            store.models_dir,
                            evidence_temp,
                            visual_input,
                            progress,
                            request.expected_speaker_count,
                            getattr(analyzer, "voice_cluster_count", None),
                            current.words,
                        )
                    )
                except StudioError as exc:
                    visual_status = "audio_fallback"
                    analyzer.warnings.append((exc.code, exc.message))
            if not getattr(analyzer, "voice_cluster_count", 0) and not (
                fusion_summary.face_identity_count
            ):
                speakers = []
            cues, change_summary = _build_speaker_proposal(current, speakers)
            findings = _findings_with_speaker_uncertainty(
                cues, speakers, current.media.duration
            )
            proposed_names, name_review_warnings = _reconcile_speaker_names(
                current.speaker_names, current.speakers, speakers
            )
            findings.extend(
                ValidationFinding(
                    code="speaker_name_review",
                    message=warning,
                    severity=Severity.WARNING,
                )
                for warning in name_review_warnings
            )
            findings.extend(
                ValidationFinding(
                    code=code,
                    message=f"Optional automatic feature skipped: {message}",
                    severity=Severity.WARNING,
                )
                for code, message in analyzer.warnings
            )
            job.result = {
                "type": "speaker_proposal",
                "base_updated_at": base_updated_at,
                "expected_speaker_count": request.expected_speaker_count,
                "detected_count": len({turn.speaker for turn in speakers}),
                "speakers": [turn.model_dump(mode="json") for turn in speakers],
                "words": [word.model_dump(mode="json") for word in current.words],
                "face_tracks": [track.model_dump(mode="json") for track in face_tracks],
                "visual_speaker_status": visual_status,
                "speaker_engine": "sface_ecapa_v1",
                "fusion_summary": fusion_summary.model_dump(mode="json"),
                "speaker_names": proposed_names,
                "name_review_warnings": name_review_warnings,
                "evidence_temp": evidence_temp.name if evidence_temp.is_file() else None,
                "cues": [cue.model_dump(mode="json") for cue in cues],
                "findings": [finding.model_dump(mode="json") for finding in findings],
                "change_summary": change_summary,
            }
            progress("Review speaker changes", 95, "A non-destructive preview is ready")

        return jobs.start(
            project_id,
            "speaker-reanalysis",
            target,
            parameters={"expected_speaker_count": request.expected_speaker_count},
        )

    @app.post("/api/projects/{project_id}/speaker-proposals/{job_id}/apply")
    def apply_speaker_proposal(project_id: str, job_id: str) -> Project:
        project = _get_project(store, project_id)
        try:
            job = jobs.get(project_id, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Speaker proposal not found") from exc
        result = job.result or {}
        if job.state != JobState.COMPLETED or result.get("type") != "speaker_proposal":
            raise HTTPException(status_code=400, detail="Speaker proposal is not ready")
        if project.updated_at.isoformat() != result.get("base_updated_at"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "speaker_proposal_stale",
                    "message": (
                        "Captions changed after speaker analysis began. "
                        "Run Re-detect speakers again."
                    ),
                },
            )
        project.expected_speaker_count = result.get("expected_speaker_count")
        project.speakers = [SpeakerTurn.model_validate(item) for item in result["speakers"]]
        if result.get("words"):
            project.words = [WordToken.model_validate(item) for item in result["words"]]
        project.face_tracks = result.get("face_tracks", [])
        project.visual_speaker_status = result.get("visual_speaker_status", "not_analyzed")
        project.speaker_engine = result.get("speaker_engine", "sface_ecapa_v1")
        project.fusion_summary = FusionSummary.model_validate(
            result.get("fusion_summary", {})
        )
        project.speaker_names = result.get("speaker_names", {})
        project.cues = [CaptionCue.model_validate(item) for item in result["cues"]]
        project.findings = [
            ValidationFinding.model_validate(item) for item in result["findings"]
        ]
        evidence_name = result.get("evidence_temp")
        if evidence_name:
            source = store.project_dir(project_id) / safe_filename(evidence_name)
            if source.is_file():
                source.replace(store.project_dir(project_id) / "speaker-evidence.json")
        return store.save(project)

    @app.post("/api/projects/{project_id}/repair-transcript", status_code=202)
    def repair_transcript(project_id: str) -> Any:
        project = _get_project(store, project_id)
        _require_original_caption_track(project)
        if not project.media or not project.words:
            raise HTTPException(
                status_code=400,
                detail="Run automatic caption analysis before improving the transcript",
            )
        base_updated_at = project.updated_at.isoformat()

        def target(job: Any, progress: Callable[[str, int, str], None]) -> None:
            current = store.get(project_id)
            project_dir = store.project_dir(project_id)
            audio = project_dir / "analysis.wav"
            if not audio.is_file():
                progress("Preparing audio", 5, "Extracting the local analysis track")
                extract_audio(project_dir / current.media.stored_name, audio, progress)
            cuts: list[float] = []
            evidence_path = project_dir / "speaker-evidence.json"
            if evidence_path.is_file():
                try:
                    cuts = json.loads(evidence_path.read_text(encoding="utf-8")).get(
                        "camera_cuts", []
                    )
                except (OSError, ValueError):
                    cuts = []
            analyzer = LocalAnalyzer(
                store.models_dir,
                current.transcription_quality,
                current.transcription_language,
                current.sdh_mode,
            )
            recovered_words, recovery_summary = analyzer.recover_transcription(
                audio, current.words, progress, cuts
            )
            progress("Comparing voices", 58, "Refreshing voices for recovered dialogue")
            speakers = analyzer.diarize(
                audio,
                recovered_words,
                progress,
                current.expected_speaker_count,
            )
            face_tracks = current.face_tracks
            visual_status = current.visual_speaker_status
            fusion_summary = FusionSummary(
                voice_cluster_count=getattr(analyzer, "voice_cluster_count", 0),
                final_speaker_count=len({turn.speaker for turn in speakers}),
            )
            evidence_temp = project_dir / f"transcript-evidence-{job.id}.json"
            if current.media.has_video and speakers:
                try:
                    speakers, face_tracks, visual_status, fusion_summary = (
                        analyze_active_speakers(
                            project_dir / current.media.stored_name,
                            audio,
                            store.models_dir,
                            evidence_temp,
                            speakers,
                            progress,
                            current.expected_speaker_count,
                            getattr(analyzer, "voice_cluster_count", None),
                            recovered_words,
                        )
                    )
                except StudioError as exc:
                    visual_status = "audio_fallback"
                    analyzer.warnings.append((exc.code, exc.message))
            generated = segment_words_by_speaker(recovered_words, speakers)
            proposed_cues, conflicts = _build_transcript_proposal(
                current,
                generated,
                recovery_summary.get("regions", []),
                speakers,
            )
            findings = _findings_with_speaker_uncertainty(
                proposed_cues, speakers, current.media.duration
            )
            findings.extend(
                ValidationFinding(
                    code="transcript_edit_conflict",
                    message=(
                        "An edited caption overlaps recovered dialogue and was preserved. "
                        "Review it before applying."
                    ),
                    severity=Severity.WARNING,
                    cue_id=cue_id,
                )
                for cue_id in conflicts
            )
            job.result = {
                "type": "transcript_proposal",
                "base_updated_at": base_updated_at,
                "words": [word.model_dump(mode="json") for word in recovered_words],
                "speakers": [turn.model_dump(mode="json") for turn in speakers],
                "cues": [cue.model_dump(mode="json") for cue in proposed_cues],
                "findings": [finding.model_dump(mode="json") for finding in findings],
                "face_tracks": [track.model_dump(mode="json") for track in face_tracks],
                "visual_speaker_status": visual_status,
                "speaker_engine": "sface_ecapa_v1",
                "fusion_summary": fusion_summary.model_dump(mode="json"),
                "recovery_summary": recovery_summary,
                "edit_conflicts": conflicts,
                "evidence_temp": evidence_temp.name if evidence_temp.is_file() else None,
            }
            progress("Review recovered dialogue", 96, "A non-destructive preview is ready")

        return jobs.start(project_id, "transcript-repair", target)

    @app.post("/api/projects/{project_id}/transcript-proposals/{job_id}/apply")
    def apply_transcript_proposal(project_id: str, job_id: str) -> Project:
        project = _get_project(store, project_id)
        try:
            job = jobs.get(project_id, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Transcript proposal not found") from exc
        result = job.result or {}
        if job.state != JobState.COMPLETED or result.get("type") != "transcript_proposal":
            raise HTTPException(status_code=400, detail="Transcript proposal is not ready")
        if project.updated_at.isoformat() != result.get("base_updated_at"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "transcript_proposal_stale",
                    "message": (
                        "Captions changed after transcript recovery began. "
                        "Run Improve transcription again."
                    ),
                },
            )
        project.words = [WordToken.model_validate(item) for item in result["words"]]
        project.speakers = [SpeakerTurn.model_validate(item) for item in result["speakers"]]
        project.cues = [CaptionCue.model_validate(item) for item in result["cues"]]
        project.findings = [
            ValidationFinding.model_validate(item) for item in result["findings"]
        ]
        project.face_tracks = result.get("face_tracks", [])
        project.visual_speaker_status = result.get("visual_speaker_status", "not_analyzed")
        project.speaker_engine = result.get("speaker_engine", "sface_ecapa_v1")
        project.fusion_summary = FusionSummary.model_validate(
            result.get("fusion_summary", {})
        )
        evidence_name = result.get("evidence_temp")
        if evidence_name:
            source = store.project_dir(project_id) / safe_filename(evidence_name)
            if source.is_file():
                source.replace(store.project_dir(project_id) / "speaker-evidence.json")
        return store.save(project)

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

    @app.get("/api/projects/{project_id}/speaker-evidence")
    def speaker_evidence(project_id: str, start: float = 0, end: float = 30) -> dict[str, Any]:
        _get_project(store, project_id)
        if start < 0 or end <= start or end - start > 60:
            raise HTTPException(status_code=400, detail="Request a valid interval up to 60 seconds")
        path = store.project_dir(project_id) / "speaker-evidence.json"
        if not path.is_file():
            return {"tracks": []}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"tracks": []}
        return {
            "tracks": [
                {
                    "id": track.get("id"),
                    "speaker": track.get("speaker"),
                    "samples": [
                        sample
                        for sample in track.get("samples", [])
                        if start <= float(sample.get("time", -1)) <= end
                    ],
                }
                for track in payload.get("tracks", [])
                if any(start <= float(s.get("time", -1)) <= end for s in track.get("samples", []))
            ]
        }

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
        if format_name in {"srt", "vtt", "ttml", "html", "report"}:
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
                job_context=progress,
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
        all_exports = [
            item
            for track in project.caption_tracks
            for item in track.exports
        ]
        if not any(item.filename == safe for item in [*project.exports, *all_exports]):
            raise HTTPException(status_code=404, detail="Export not found")
        path = store.project_dir(project_id) / "exports" / safe
        return FileResponse(
            path,
            filename=safe,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

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

    register_localization_routes(app, store, jobs)

    register_roadmap_routes(
        app,
        store,
        jobs,
        {
            "analysis": lambda project_id, _job: analyze_project(project_id),
            "mp4-export": lambda project_id, _job: create_export(project_id, "mp4"),
            "transcript-repair": lambda project_id, _job: repair_transcript(project_id),
            "speaker-reanalysis": lambda project_id, job: reanalyze_speakers(
                project_id,
                SpeakerReanalysisRequest(
                    expected_speaker_count=job.parameters.get("expected_speaker_count")
                ),
            ),
            "overlap-analysis": lambda project_id, job: analyze_overlap(
                project_id,
                OverlapRequest(
                    start=float(job.parameters["start"]), end=float(job.parameters["end"])
                ),
            ),
        },
        _analysis_task,
    )

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
    original_track = project.original_caption_track()
    if project.active_caption_track_id != original_track.id:
        project.activate_caption_track(original_track.id)
    if not project.media:
        raise StudioError("media_not_ready", "Media is not ready for analysis.")
    project_dir = store.project_dir(project_id)
    source = project_dir / project.media.stored_name
    audio = project_dir / "analysis.wav"
    progress("Preparing audio", 10, "Extracting a private local analysis track")
    if not audio.is_file():
        extract_audio(source, audio, progress)
    analyzer = LocalAnalyzer(
        store.models_dir,
        project.transcription_quality,
        project.spoken_language,
        project.sdh_mode,
    )
    words, speakers, sounds, cues = analyzer.analyze(
        audio, progress, project.expected_speaker_count
    )
    if speakers and not getattr(analyzer, "voice_cluster_count", 0):
        analyzer.voice_cluster_count = len({turn.speaker for turn in speakers})
    face_tracks = []
    visual_status = "not_applicable"
    fusion_summary = FusionSummary(
        voice_cluster_count=getattr(analyzer, "voice_cluster_count", 0),
        final_speaker_count=len({turn.speaker for turn in speakers}),
    )
    evidence_temp = project_dir / "speaker-evidence.pending.json"
    visual_input = speakers or _provisional_speech_turns(words)
    if project.media.has_video and visual_input:
        try:
            speakers, face_tracks, visual_status, fusion_summary = analyze_active_speakers(
                source,
                audio,
                store.models_dir,
                evidence_temp,
                visual_input,
                progress,
                project.expected_speaker_count,
                getattr(analyzer, "voice_cluster_count", None),
                words,
            )
            speech_cues = segment_words_by_speaker(words, speakers)
            sound_cues = analyzer.sound_cues(sounds, speech_cues)
            cues = sorted(
                [*speech_cues, *sound_cues],
                key=lambda cue: (cue.start, cue.end, cue.source == SourceType.SOUND),
            )
            evidence_temp.replace(project_dir / "speaker-evidence.json")
        except StudioError as exc:
            evidence_temp.unlink(missing_ok=True)
            visual_status = "audio_fallback"
            analyzer.warnings.append((exc.code, exc.message))
    if not getattr(analyzer, "voice_cluster_count", 0) and not (
        fusion_summary.face_identity_count
    ):
        speakers = []
        speech_cues = segment_words_by_speaker(words, speakers)
        sound_cues = analyzer.sound_cues(sounds, speech_cues)
        cues = sorted(
            [*speech_cues, *sound_cues],
            key=lambda cue: (cue.start, cue.end, cue.source == SourceType.SOUND),
        )
    project = store.get(project_id)
    project.words = words
    project.speakers = speakers
    project.face_tracks = face_tracks
    project.visual_speaker_status = visual_status
    project.speaker_engine = "sface_ecapa_v1"
    project.fusion_summary = fusion_summary
    project.sounds = sounds
    project.detected_language = getattr(analyzer, "detected_language", None)
    original_track = project.original_caption_track()
    original_track.language = (
        project.detected_language
        or (project.spoken_language if project.spoken_language != "auto" else "und")
    )
    project.cues = cues
    project.findings = validate_cues(cues, project.media.duration)
    project.mark_translation_tracks_stale()
    uncertain_cues: set[str] = set()
    for turn in speakers:
        if turn.confidence is None or turn.confidence >= 0.65:
            continue
        cue = max(
            cues,
            key=lambda item: max(0.0, min(item.end, turn.end) - max(item.start, turn.start)),
            default=None,
        )
        if cue and cue.id not in uncertain_cues:
            uncertain_cues.add(cue.id)
            project.findings.append(
                ValidationFinding(
                    code="uncertain_speaker",
                    message="The anonymous speaker label is uncertain; listen and verify it.",
                    severity=Severity.INFO,
                    cue_id=cue.id,
                )
            )
    for previous, current in zip(speakers, speakers[1:], strict=False):
        shared = min(previous.end, current.end) - max(previous.start, current.start)
        if previous.speaker != current.speaker and shared >= 0.15:
            cue = next(
                (
                    item
                    for item in cues
                    if item.start < min(previous.end, current.end)
                    and item.end > max(previous.start, current.start)
                ),
                None,
            )
            project.findings.append(
                ValidationFinding(
                    code="possible_overlapping_speech",
                    message=(
                        "Two voices may overlap here. Use Analyze overlapping voices "
                        "if both need separate lines."
                    ),
                    severity=Severity.INFO,
                    cue_id=cue.id if cue else None,
                )
            )
    project.findings.extend(
        ValidationFinding(
            code=code,
            message=f"Optional automatic feature skipped: {message}",
            severity=Severity.WARNING,
        )
        for code, message in analyzer.warnings
    )
    store.save(project)
    source_language = project.original_caption_track().language
    existing_translation_languages = {
        track.language for track in project.caption_tracks if track.kind == "translation"
    }
    for target_language in project.requested_caption_languages:
        if target_language == source_language or target_language in existing_translation_languages:
            continue
        try:
            progress(
                "Creating translated captions",
                96,
                f"Translating the original captions to {target_language}",
            )
            create_translation_track(
                project,
                target_language,
                store.models_dir,
                progress,
            )
            store.save(project)
            existing_translation_languages.add(target_language)
        except StudioError as exc:
            project.activate_caption_track(project.original_caption_track().id)
            project.findings.append(
                ValidationFinding(
                    code="translation_skipped",
                    message=f"Requested translation skipped: {exc.message}",
                    severity=Severity.WARNING,
                )
            )
            store.save(project)
    project.activate_caption_track(project.original_caption_track().id)
    store.save(project)
    progress("Saving", 99, "Saving caption tracks and accessibility findings")


def _parse_target_caption_languages(value: str) -> list[str]:
    try:
        raw = json.loads(value or "[]")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Caption languages are invalid") from exc
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="Caption languages are invalid")
    try:
        return normalize_target_languages([str(item) for item in raw])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _require_original_caption_track(project: Project) -> None:
    if project.active_caption_track().kind != "original":
        raise HTTPException(
            status_code=409,
            detail=(
                "This analysis tool works on the original spoken-language caption track. "
                "Switch to the Original track first."
            ),
        )


def _normalized_caption_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _build_speaker_proposal(
    project: Project, speakers: list[SpeakerTurn]
) -> tuple[list[CaptionCue], dict[str, int]]:
    """Apply speaker evidence to copies of cues without overwriting edited caption text."""

    proposed: list[CaptionCue] = []
    splits = 0
    original_speakers = {cue.id: cue.speaker for cue in project.cues}
    for cue in project.cues:
        copied = cue.model_copy(deep=True)
        if cue.source == SourceType.SOUND or cue.overlap_group_id:
            proposed.append(copied)
            continue
        words = [
            word
            for word in project.words
            if cue.start <= (word.start + word.end) / 2 <= cue.end
        ]
        parts = segment_words_by_speaker(words, speakers) if words else []
        automatic_text_matches = (
            cue.source == SourceType.TRANSCRIPTION
            and parts
            and _normalized_caption_text(" ".join(part.text for part in parts))
            == _normalized_caption_text(cue.text)
        )
        if automatic_text_matches and len(parts) > 1:
            splits += len(parts) - 1
            for index, part in enumerate(parts):
                replacement = copied.model_copy(deep=True)
                if index:
                    replacement.id = part.id
                replacement.start = cue.start if index == 0 else part.start
                replacement.end = cue.end if index == len(parts) - 1 else part.end
                replacement.text = part.text
                replacement.speaker = part.speaker
                if replacement.confidence is not None and part.confidence is not None:
                    replacement.confidence = min(replacement.confidence, part.confidence)
                proposed.append(replacement)
        else:
            copied.speaker, speaker_confidence = speaker_for_interval(
                cue.start, cue.end, speakers
            )
            if copied.confidence is not None and speaker_confidence is not None:
                copied.confidence = min(copied.confidence, speaker_confidence)
            proposed.append(copied)

    joined: list[CaptionCue] = []
    joins = 0
    for cue in proposed:
        previous = joined[-1] if joined else None
        can_join = bool(
            previous
            and previous.source == SourceType.TRANSCRIPTION
            and cue.source == SourceType.TRANSCRIPTION
            and not previous.overlap_group_id
            and not cue.overlap_group_id
            and previous.speaker == cue.speaker
            and cue.start - previous.end <= 0.05
            and original_speakers.get(previous.id) != original_speakers.get(cue.id)
            and not re.search(r"[.!?][\"']?$", previous.text.strip())
            and cue.end - previous.start <= 7.0
            and len(f"{previous.text} {cue.text}") <= 84
        )
        if can_join and previous:
            previous.end = cue.end
            previous.text = f"{previous.text} {cue.text}".strip()
            if previous.confidence is not None and cue.confidence is not None:
                previous.confidence = min(previous.confidence, cue.confidence)
            joins += 1
        else:
            joined.append(cue)

    label_changes = sum(
        1
        for cue in joined
        if cue.id in original_speakers and cue.speaker != original_speakers[cue.id]
    )
    uncertain = sum(
        1 for turn in speakers if turn.confidence is None or turn.confidence < 0.65
    )
    return joined, {
        "label_changes": label_changes,
        "joins": joins,
        "splits": splits,
        "uncertain_samples": uncertain,
    }


def _findings_with_speaker_uncertainty(
    cues: list[CaptionCue], speakers: list[SpeakerTurn], duration: float | None
) -> list[ValidationFinding]:
    findings = validate_cues(cues, duration)
    reported: set[str] = set()
    for turn in speakers:
        if turn.confidence is not None and turn.confidence >= 0.65:
            continue
        cue = max(
            cues,
            key=lambda item: max(0.0, min(item.end, turn.end) - max(item.start, turn.start)),
            default=None,
        )
        if cue and cue.id not in reported:
            reported.add(cue.id)
            findings.append(
                ValidationFinding(
                    code="uncertain_speaker",
                    message="The anonymous speaker label is uncertain; listen and verify it.",
                    severity=Severity.INFO,
                    cue_id=cue.id,
                )
            )
    return findings


def _overlaps_regions(
    start: float, end: float, regions: list[tuple[float, float]] | list[list[float]]
) -> bool:
    return any(start < region_end and end > region_start for region_start, region_end in regions)


def _cue_matches_saved_words(cue: CaptionCue, words: list[WordToken]) -> bool:
    text = " ".join(
        word.text
        for word in words
        if cue.start <= (word.start + word.end) / 2 <= cue.end
    )
    return _normalized_caption_text(text) == _normalized_caption_text(cue.text)


def _build_transcript_proposal(
    project: Project,
    generated: list[CaptionCue],
    regions: list[tuple[float, float]] | list[list[float]],
    speakers: list[SpeakerTurn],
) -> tuple[list[CaptionCue], list[str]]:
    """Replace only automatic captions in recovery regions and preserve user edits."""

    retained: list[CaptionCue] = []
    conflicts: list[str] = []
    replaced: list[CaptionCue] = []
    for cue in project.cues:
        affected = _overlaps_regions(cue.start, cue.end, regions)
        edited = cue.source == SourceType.TRANSCRIPTION and not _cue_matches_saved_words(
            cue, project.words
        )
        if cue.source != SourceType.TRANSCRIPTION or not affected or edited:
            copied = cue.model_copy(deep=True)
            if cue.source == SourceType.TRANSCRIPTION:
                copied.speaker, _confidence = speaker_for_interval(
                    copied.start, copied.end, speakers
                )
            retained.append(copied)
            if affected and edited:
                conflicts.append(cue.id)
        else:
            replaced.append(cue)

    additions = [
        cue.model_copy(deep=True)
        for cue in generated
        if _overlaps_regions(cue.start, cue.end, regions)
        and not any(
            conflict.start < cue.end and conflict.end > cue.start
            for conflict in retained
            if conflict.id in conflicts
        )
    ]
    available_ids = [cue.id for cue in replaced]
    for cue, cue_id in zip(additions, available_ids, strict=False):
        cue.id = cue_id
    return sorted(
        [*retained, *additions],
        key=lambda cue: (cue.start, cue.end, cue.source == SourceType.SOUND),
    ), conflicts


def _provisional_speech_turns(words: list[Any]) -> list[SpeakerTurn]:
    """Provide speech timing to the face worker without claiming a voice identity."""

    return [
        SpeakerTurn(
            speaker="Speaker 1",
            start=start,
            end=end,
            confidence=None,
            audio_confidence=None,
            method="uncertain",
        )
        for start, end in LocalAnalyzer._speaker_windows(words)
    ]


def _reconcile_speaker_names(
    names: dict[str, str],
    previous: list[SpeakerTurn],
    proposed: list[SpeakerTurn],
) -> tuple[dict[str, str], list[str]]:
    """Carry display names only across a strong temporal speaker match."""

    if not names:
        return {}, []
    reconciled: dict[str, str] = {}
    warnings: list[str] = []
    claimed: set[str] = set()
    for old_speaker, display_name in names.items():
        old_turns = [turn for turn in previous if turn.speaker == old_speaker]
        total = sum(max(0.0, turn.end - turn.start) for turn in old_turns)
        overlap: dict[str, float] = {}
        for old_turn in old_turns:
            for new_turn in proposed:
                shared = max(
                    0.0,
                    min(old_turn.end, new_turn.end) - max(old_turn.start, new_turn.start),
                )
                if shared:
                    overlap[new_turn.speaker] = overlap.get(new_turn.speaker, 0.0) + shared
        best = max(overlap, key=overlap.get) if overlap else None
        ratio = overlap.get(best, 0.0) / total if best and total else 0.0
        if best and ratio >= 0.65 and best not in claimed:
            reconciled[best] = display_name
            claimed.add(best)
        else:
            warnings.append(
                f'The display name "{display_name}" was not carried forward because '
                "its new anonymous speaker match is uncertain. Review and rename it after applying."
            )
    return reconciled, warnings


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
