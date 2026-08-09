from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from uuid import uuid4

from .migrations import CURRENT_PROJECT_SCHEMA_VERSION, migrate_project_payload
from .models import AnalysisJob, Project, StorageSummary, path_size, utc_now

_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")
_MAX_FILENAME_LENGTH = 150


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

    def save(self, project: Project) -> Project:
        with self._lock:
            project.schema_version = CURRENT_PROJECT_SCHEMA_VERSION
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
    def _atomic_write_text(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def _project_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"
