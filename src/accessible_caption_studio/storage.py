from __future__ import annotations

import hashlib
import json
import re
import shutil
import threading
import zipfile
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .migrations import CURRENT_PROJECT_SCHEMA_VERSION, migrate_project_payload
from .models import AnalysisJob, Project, StorageSummary, path_size, utc_now

_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")
_MAX_FILENAME_LENGTH = 150
_MAX_REVISIONS = 50
_ARCHIVE_FORMAT_VERSION = 1


def safe_filename(value: str, fallback: str = "media") -> str:
    cleaned = _SAFE.sub("", Path(value).name).strip(" .")
    if not cleaned:
        return fallback
    if len(cleaned) <= _MAX_FILENAME_LENGTH:
        return cleaned

    path = Path(cleaned)
    suffix = path.suffix
    if suffix and len(suffix) < _MAX_FILENAME_LENGTH:
        available_stem_length = _MAX_FILENAME_LENGTH - len(suffix)
        stem = path.stem[:available_stem_length].rstrip(" .")
        if stem:
            return f"{stem}{suffix}"

    return cleaned[:_MAX_FILENAME_LENGTH].rstrip(" .") or fallback


def _revision_fingerprint(project: Project) -> str:
    payload = project.model_dump(
        mode="json",
        exclude={"updated_at", "latest_job_id", "exports"},
    )
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class ProjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.projects_dir = self.root / "projects"
        self.models_dir = self.root / "models"
        self.temp_dir = self.root / "temporary"
        self.settings_path = self.root / "settings.json"
        self._lock = threading.RLock()
        for path in (self.projects_dir, self.models_dir, self.temp_dir):
            path.mkdir(parents=True, exist_ok=True)

    def create(self, name: str) -> Project:
        project = Project(name=name, schema_version=CURRENT_PROJECT_SCHEMA_VERSION)
        self.project_dir(project.id).mkdir(parents=True, exist_ok=False)
        (self.project_dir(project.id) / "exports").mkdir()
        self.save(project)
        return project

    def list(self) -> list[Project]:
        projects = []
        for path in self.projects_dir.glob("*/project.json"):
            try:
                projects.append(self._load_project(path))
            except (OSError, ValueError):
                continue
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def get(self, project_id: str) -> Project:
        path = self._project_file(project_id)
        if not path.is_file():
            raise KeyError(project_id)
        return self._load_project(path)

    def save(self, project: Project, *, touch: bool = True) -> Project:
        with self._lock:
            project.sync_active_caption_track()
            project.schema_version = CURRENT_PROJECT_SCHEMA_VERSION
            if touch:
                project.updated_at = utc_now()
            path = self._project_file(project.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write_text(path, project.model_dump_json(indent=2))
        return project

    def delete(self, project_id: str) -> None:
        path = self.project_dir(project_id)
        if not path.is_dir():
            raise KeyError(project_id)
        shutil.rmtree(path)

    def duplicate(self, project_id: str) -> Project:
        source = self.get(project_id)
        duplicate = Project.model_validate(source.model_dump())
        duplicate.id = uuid4().hex
        duplicate.name = f"{source.name} copy"
        duplicate.exports = []
        for track in duplicate.caption_tracks:
            track.exports = []
        duplicate.refresh_caption_track_view()
        duplicate.latest_job_id = None
        duplicate.is_favorite = False
        target_dir = self.project_dir(duplicate.id)
        target_dir.mkdir(parents=True)
        (target_dir / "exports").mkdir()
        if source.media:
            source_media = self.project_dir(source.id) / source.media.stored_name
            if source_media.is_file():
                shutil.copy2(source_media, target_dir / source.media.stored_name)
        audio = self.project_dir(source.id) / "analysis.wav"
        if audio.is_file():
            shutil.copy2(audio, target_dir / audio.name)
        evidence = self.project_dir(source.id) / "speaker-evidence.json"
        if evidence.is_file():
            shutil.copy2(evidence, target_dir / evidence.name)
        return self.save(duplicate)

    def project_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise KeyError(project_id)
        return self.projects_dir / project_id

    def write_job(self, job: AnalysisJob) -> None:
        jobs = self.project_dir(job.project_id) / "jobs"
        jobs.mkdir(exist_ok=True)
        path = jobs / f"{job.id}.json"
        self._atomic_write_text(path, job.model_dump_json(indent=2))

    def read_job(self, project_id: str, job_id: str) -> AnalysisJob:
        path = self.project_dir(project_id) / "jobs" / f"{safe_filename(job_id)}.json"
        if not path.is_file():
            raise KeyError(job_id)
        return AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))

    def list_jobs(self) -> list[AnalysisJob]:
        jobs: list[AnalysisJob] = []
        for path in self.projects_dir.glob("*/jobs/*.json"):
            try:
                jobs.append(AnalysisJob.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return jobs

    def cleanup_partial_artifacts(self, project_id: str) -> int:
        project_dir = self.project_dir(project_id)
        if not project_dir.is_dir():
            return 0
        removed = 0
        for path in list(project_dir.rglob("*")):
            if path.is_file() and (".partial" in path.name or path.suffix == ".tmp"):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    continue
        for path in list(project_dir.glob(".caption-render-*")):
            if path.is_dir():
                try:
                    shutil.rmtree(path)
                    removed += 1
                except OSError:
                    continue
        return removed

    def create_revision(self, project: Project, reason: str = "Automatic edit checkpoint") -> dict[str, object] | None:
        revisions_dir = self.project_dir(project.id) / "revisions"
        revisions_dir.mkdir(parents=True, exist_ok=True)
        fingerprint = _revision_fingerprint(project)
        existing = sorted(revisions_dir.glob("*.json"), reverse=True)
        if existing:
            try:
                latest = json.loads(existing[0].read_text(encoding="utf-8"))
                if latest.get("fingerprint") == fingerprint:
                    return None
            except (OSError, ValueError):
                pass

        created_at = utc_now()
        revision_id = f"{created_at.strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}"
        payload = {
            "id": revision_id,
            "created_at": created_at.isoformat(),
            "reason": " ".join(str(reason).split()).strip()[:120] or "Automatic edit checkpoint",
            "fingerprint": fingerprint,
            "project": project.model_dump(mode="json"),
        }
        self._atomic_write_text(
            revisions_dir / f"{revision_id}.json",
            json.dumps(payload, indent=2, ensure_ascii=False),
        )
        existing = sorted(revisions_dir.glob("*.json"), reverse=True)
        for old in existing[_MAX_REVISIONS:]:
            old.unlink(missing_ok=True)
        return self._revision_summary(payload)

    def list_revisions(self, project_id: str) -> list[dict[str, object]]:
        revisions_dir = self.project_dir(project_id) / "revisions"
        if not revisions_dir.is_dir():
            return []
        revisions: list[dict[str, object]] = []
        for path in sorted(revisions_dir.glob("*.json"), reverse=True):
            try:
                revisions.append(self._revision_summary(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError):
                continue
        return revisions

    def restore_revision(self, project_id: str, revision_id: str) -> Project:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", revision_id):
            raise KeyError(revision_id)
        revision_path = self.project_dir(project_id) / "revisions" / f"{revision_id}.json"
        if not revision_path.is_file():
            raise KeyError(revision_id)
        wrapper = json.loads(revision_path.read_text(encoding="utf-8"))
        snapshot_payload = wrapper.get("project")
        if not isinstance(snapshot_payload, dict):
            raise ValueError("Revision data is invalid")
        migrated, _changed = migrate_project_payload(snapshot_payload)
        restored = Project.model_validate(migrated)
        current = self.get(project_id)
        self.create_revision(current, "Before restoring an earlier version")

        restored.id = current.id
        restored.created_at = current.created_at
        restored.media = current.media
        restored.exports = current.exports
        restored.latest_job_id = current.latest_job_id
        restored.is_favorite = current.is_favorite
        return self.save(restored)

    def create_archive(self, project_id: str) -> Path:
        project = self.get(project_id)
        project_dir = self.project_dir(project_id)
        base = safe_filename(project.name, "Accessible Caption Studio project")
        destination = self.temp_dir / f"{base}-{uuid4().hex[:8]}.acstudio.zip"
        manifest = {
            "format": "accessible-caption-studio-project",
            "archive_version": _ARCHIVE_FORMAT_VERSION,
            "project_schema_version": CURRENT_PROJECT_SCHEMA_VERSION,
            "project_name": project.name,
            "exported_at": utc_now().isoformat(),
        }
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("archive-manifest.json", json.dumps(manifest, indent=2))
            for source in sorted(project_dir.rglob("*")):
                if not source.is_file():
                    continue
                relative = source.relative_to(project_dir)
                if "jobs" in relative.parts:
                    continue
                if any(part.startswith(".caption-render-") for part in relative.parts):
                    continue
                if ".partial" in source.name or source.suffix == ".tmp":
                    continue
                archive.write(source, relative.as_posix())
        return destination

    def restore_archive(self, archive_path: Path) -> Project:
        if not zipfile.is_zipfile(archive_path):
            raise ValueError("Choose a valid Accessible Caption Studio backup ZIP file")

        staging = self.temp_dir / f".restore-{uuid4().hex}"
        staging.mkdir(parents=True, exist_ok=False)
        try:
            with zipfile.ZipFile(archive_path, "r") as archive:
                members = archive.infolist()
                if len(members) > 10000:
                    raise ValueError("The backup contains too many files")
                total_size = sum(member.file_size for member in members if not member.is_dir())
                if total_size > max(0, shutil.disk_usage(self.root).free - 100 * 1024 * 1024):
                    raise ValueError("There is not enough free disk space to restore this backup")

                names = {member.filename for member in members}
                if "project.json" not in names or "archive-manifest.json" not in names:
                    raise ValueError("This ZIP is not an Accessible Caption Studio project backup")

                try:
                    manifest = json.loads(archive.read("archive-manifest.json").decode("utf-8"))
                except (KeyError, UnicodeDecodeError, ValueError) as exc:
                    raise ValueError("The backup manifest is invalid") from exc
                if manifest.get("format") != "accessible-caption-studio-project":
                    raise ValueError("This ZIP is not an Accessible Caption Studio project backup")
                if int(manifest.get("archive_version", 0)) > _ARCHIVE_FORMAT_VERSION:
                    raise ValueError("This backup was created by a newer Accessible Caption Studio version")

                for member in members:
                    if member.is_dir() or member.filename == "archive-manifest.json":
                        continue
                    relative = PurePosixPath(member.filename)
                    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                        raise ValueError("The backup contains an unsafe file path")
                    if "jobs" in relative.parts:
                        continue
                    destination = staging.joinpath(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(member, "r") as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)

            project_path = staging / "project.json"
            payload = json.loads(project_path.read_text(encoding="utf-8"))
            migrated, _changed = migrate_project_payload(payload)
            project = Project.model_validate(migrated)
            project.id = uuid4().hex
            project.latest_job_id = None
            project.schema_version = CURRENT_PROJECT_SCHEMA_VERSION

            if project.media:
                media_path = staging / project.media.stored_name
                if not media_path.is_file():
                    raise ValueError("The backup is missing its project media file")

            target_dir = self.project_dir(project.id)
            if target_dir.exists():
                raise ValueError("Could not allocate storage for the restored project")
            staging.replace(target_dir)
            (target_dir / "exports").mkdir(exist_ok=True)
            return self.save(project)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise

    def settings(self) -> dict[str, str]:
        if not self.settings_path.is_file():
            return {}
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return {str(key): str(value) for key, value in data.items()}
        except (OSError, ValueError):
            return {}

    def summary(self) -> StorageSummary:
        return StorageSummary(
            projects_bytes=path_size(self.projects_dir),
            models_bytes=path_size(self.models_dir),
            temporary_bytes=path_size(self.temp_dir),
            project_count=len(self.list()),
        )

    def clear_cache(self, target: str) -> None:
        path = {"models": self.models_dir, "temporary": self.temp_dir}.get(target)
        if path is None:
            raise ValueError("only model or temporary caches can be cleared")
        shutil.rmtree(path)
        path.mkdir(parents=True)

    def _load_project(self, path: Path) -> Project:
        payload = json.loads(path.read_text(encoding="utf-8"))
        migrated, changed = migrate_project_payload(payload)
        project = Project.model_validate(migrated)
        if changed:
            with self._lock:
                self._atomic_write_text(path, project.model_dump_json(indent=2))
        return project

    @staticmethod
    def _revision_summary(payload: dict[str, object]) -> dict[str, object]:
        project = payload.get("project")
        project_data = project if isinstance(project, dict) else {}
        cues = project_data.get("cues")
        return {
            "id": str(payload.get("id") or ""),
            "created_at": str(payload.get("created_at") or ""),
            "reason": str(payload.get("reason") or "Automatic edit checkpoint"),
            "name": str(project_data.get("name") or "Untitled project"),
            "cue_count": len(cues) if isinstance(cues, list) else 0,
        }

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def _project_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"
