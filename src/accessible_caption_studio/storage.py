from __future__ import annotations

import json
import re
import shutil
import threading
from pathlib import Path
from uuid import uuid4

from .models import AnalysisJob, Project, StorageSummary, path_size, utc_now

_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def safe_filename(value: str, fallback: str = "media") -> str:
    cleaned = _SAFE.sub("", Path(value).name).strip(" .")
    return cleaned[:150] or fallback


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
        project = Project(name=name)
        self.project_dir(project.id).mkdir(parents=True, exist_ok=False)
        (self.project_dir(project.id) / "exports").mkdir()
        self.save(project)
        return project

    def list(self) -> list[Project]:
        projects = []
        for path in self.projects_dir.glob("*/project.json"):
            try:
                projects.append(Project.model_validate_json(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return sorted(projects, key=lambda item: item.updated_at, reverse=True)

    def get(self, project_id: str) -> Project:
        path = self._project_file(project_id)
        if not path.is_file():
            raise KeyError(project_id)
        return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, project: Project) -> Project:
        with self._lock:
            project.updated_at = utc_now()
            path = self._project_file(project.id)
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(project.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(path)
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
        return self.save(duplicate)

    def project_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", project_id):
            raise KeyError(project_id)
        return self.projects_dir / project_id

    def write_job(self, job: AnalysisJob) -> None:
        jobs = self.project_dir(job.project_id) / "jobs"
        jobs.mkdir(exist_ok=True)
        path = jobs / f"{job.id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)

    def read_job(self, project_id: str, job_id: str) -> AnalysisJob:
        path = self.project_dir(project_id) / "jobs" / f"{safe_filename(job_id)}.json"
        if not path.is_file():
            raise KeyError(job_id)
        return AnalysisJob.model_validate_json(path.read_text(encoding="utf-8"))

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

    def _project_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"
