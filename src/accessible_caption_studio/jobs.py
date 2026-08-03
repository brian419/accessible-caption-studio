from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable

from .models import AnalysisJob, JobState, utc_now
from .storage import ProjectStore


class JobProgress:
    """Callable progress reporter that also owns cancellable child processes."""

    def __init__(self, manager: JobManager, job: AnalysisJob) -> None:
        self.manager = manager
        self.job = job
        self.cancelled = threading.Event()
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.RLock()

    def __call__(self, stage: str, percent: int, message: str = "") -> None:
        if self.cancelled.is_set():
            raise InterruptedError("Job cancelled")
        self.job.stage = stage
        self.job.progress = max(self.job.progress, min(99, percent))
        self.job.message = message
        self.manager._persist(self.job)

    def run_process(
        self, command: list[str], *, capture_output: bool = True
    ) -> subprocess.CompletedProcess[str]:
        self.check_cancelled()
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=True,
            start_new_session=True,
        )
        with self._lock:
            self._process = process
        try:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if self.cancelled.is_set():
                    self._terminate(process)
                    raise InterruptedError("Job cancelled")
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None

    def check_cancelled(self) -> None:
        if self.cancelled.is_set():
            raise InterruptedError("Job cancelled")

    def register_process(self, process: subprocess.Popen[str]) -> None:
        self.check_cancelled()
        with self._lock:
            self._process = process

    def unregister_process(self, process: subprocess.Popen[str]) -> None:
        with self._lock:
            if self._process is process:
                self._process = None

    def cancel(self) -> None:
        self.cancelled.set()
        with self._lock:
            process = self._process
        if process and process.poll() is None:
            threading.Thread(target=self._terminate, args=(process,), daemon=True).start()

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
        deadline = time.monotonic() + 2
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                process.kill()


class JobManager:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self._jobs: dict[str, AnalysisJob] = {}
        self._cancelled: set[str] = set()
        self._contexts: dict[str, JobProgress] = {}
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
            if job.state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
                return job
            was_queued = job.state == JobState.QUEUED
            self._cancelled.add(job_id)
            job.state = JobState.CANCELLING
            job.stage = "Cancelling"
            job.message = "Stopping the active process and cleaning up partial files…"
            self._persist(job)
            context = self._contexts.get(job_id)
            if context:
                context.cancel()
            elif was_queued:
                job.state = JobState.CANCELLED
                job.stage = "Cancelled"
                self._persist(job)
        return job

    def _run(
        self,
        job: AnalysisJob,
        target: Callable[[AnalysisJob, Callable[[str, int, str], None]], None],
    ) -> None:
        progress = JobProgress(self, job)
        with self._lock:
            self._contexts[job.id] = progress
        if job.id in self._cancelled:
            progress.cancel()
        else:
            job.state = JobState.RUNNING
            self._persist(job)

        try:
            target(job, progress)
            progress.check_cancelled()
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
            with self._lock:
                self._contexts.pop(job.id, None)
            self._persist(job)

    def _persist(self, job: AnalysisJob) -> None:
        job.updated_at = utc_now()
        with self._lock:
            self._jobs[job.id] = job
            self.store.write_job(job)
