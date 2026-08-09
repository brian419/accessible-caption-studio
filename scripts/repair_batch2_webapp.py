from __future__ import annotations

from pathlib import Path

PATH = Path("src/accessible_caption_studio/webapp.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one {label} target, found {count}")
    return text.replace(old, new, 1)


text = PATH.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from pydantic import BaseModel, Field\n",
    "from pydantic import BaseModel, Field\nfrom starlette.background import BackgroundTask\n",
    "BackgroundTask import",
)
text = replace_once(
    text,
    "from .visual import analyze_active_speakers\n",
    "from .visual import analyze_active_speakers\nfrom .waveform import build_waveform_envelope\n",
    "waveform import",
)
text = replace_once(
    text,
    '''class OverlapRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
''',
    '''class FavoriteRequest(BaseModel):
    favorite: bool


class OverlapRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
''',
    "FavoriteRequest",
)

restore_route = '''    @app.post("/api/projects/restore", status_code=201)
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

'''
text = replace_once(
    text,
    '    @app.post("/api/projects/upload", status_code=202)\n',
    restore_route + '    @app.post("/api/projects/upload", status_code=202)\n',
    "project restore route",
)

utility_routes = '''    @app.post("/api/projects/{project_id}/favorite")
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

'''
text = replace_once(
    text,
    '''    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> Project:
        return _get_project(store, project_id)

''',
    utility_routes
    + '''    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> Project:
        return _get_project(store, project_id)

''',
    "project utility routes",
)

old_update = '''    @app.patch("/api/projects/{project_id}")
    def update_project(project_id: str, request: ProjectUpdate) -> Project:
        project = _get_project(store, project_id)
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
'''
new_update = '''    @app.patch("/api/projects/{project_id}")
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
        if request.caption_style is not None:
            project.caption_style = request.caption_style
        return store.save(project)
'''
text = replace_once(text, old_update, new_update, "revision-aware project update")
PATH.write_text(text, encoding="utf-8")
