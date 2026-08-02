from __future__ import annotations

import threading
from collections.abc import Callable

from .models import AnalysisJob, JobState, utc_now
from .storage import ProjectStore


class JobManager:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self._jobs: dict[str, AnalysisJob] = {}
        self._cancelled: set[str] = set()
        self._lock = threading.RLock()

    def start(
        self,
        project_id: str,
        kind: str,
        target: Callable[[AnalysisJob, Callable[[str, int, str], None]], None],
    ) -> AnalysisJob:
        job = AnalysisJob(project_id=project_id, kind=kind)
        with self._lock:
            self._jobs[job.id] = job
            self.store.write_job(job)
        thread = threading.Thread(target=self._run, args=(job, target), daemon=True)
        thread.start()
        return job

    def get(self, project_id: str, job_id: str) -> AnalysisJob:
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
        return self.store.read_job(project_id, job_id)

    def cancel(self, project_id: str, job_id: str) -> AnalysisJob:
        job = self.get(project_id, job_id)
        with self._lock:
            self._cancelled.add(job_id)
            if job.state == JobState.QUEUED:
                job.state = JobState.CANCELLED
                self._persist(job)
        return job

    def _run(
        self,
        job: AnalysisJob,
        target: Callable[[AnalysisJob, Callable[[str, int, str], None]], None],
    ) -> None:
        job.state = JobState.RUNNING
        self._persist(job)

        def progress(stage: str, percent: int, message: str = "") -> None:
            if job.id in self._cancelled:
                raise InterruptedError("Job cancelled")
            job.stage = stage
            job.progress = max(job.progress, min(99, percent))
            job.message = message
            self._persist(job)

        try:
            target(job, progress)
            job.state = JobState.COMPLETED
            job.stage = "Complete"
            job.progress = 100
        except InterruptedError:
            job.state = JobState.CANCELLED
            job.stage = "Cancelled"
            job.message = "Processing was cancelled. Saved work remains available."
        except Exception as exc:
            job.state = JobState.FAILED
            job.stage = "Needs attention"
            job.error_code = getattr(exc, "code", "processing_failed")
            job.error = str(exc)
            job.message = str(exc)
        finally:
            self._persist(job)

    def _persist(self, job: AnalysisJob) -> None:
        job.updated_at = utc_now()
        with self._lock:
            self._jobs[job.id] = job
            self.store.write_job(job)
