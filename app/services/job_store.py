"""
In-memory job store for model execution tracking.

In production, replace with Redis or a database-backed store
for multi-worker deployments.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.schemas.model import JobStatus, ScenarioMetrics, OutputFile


class JobRecord:
    __slots__ = (
        "job_id", "status", "created_at", "started_at", "completed_at",
        "progress", "error", "output_dir", "scenarios", "output_files",
        "total_elapsed_seconds", "n_policies",
    )

    def __init__(self, job_id: str) -> None:
        self.job_id: str = job_id
        self.status: JobStatus = JobStatus.pending
        self.created_at: datetime = datetime.now(timezone.utc)
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.progress: Optional[str] = None
        self.error: Optional[str] = None
        self.output_dir: Optional[str] = None
        self.scenarios: List[ScenarioMetrics] = []
        self.output_files: List[OutputFile] = []
        self.total_elapsed_seconds: Optional[float] = None
        self.n_policies: Optional[int] = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Mutation helpers (called from background thread)
    # ------------------------------------------------------------------

    def create(self, job_id: str) -> JobRecord:
        record = JobRecord(job_id)
        with self._lock:
            self._jobs[job_id] = record
        return record

    def mark_running(self, job_id: str, progress: Optional[str] = None) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.status = JobStatus.running
            rec.started_at = datetime.now(timezone.utc)
            rec.progress = progress

    def update_progress(self, job_id: str, message: str) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].progress = message

    def mark_completed(
        self,
        job_id: str,
        output_dir: str,
        scenarios: List[ScenarioMetrics],
        output_files: List[OutputFile],
        total_elapsed: float,
        n_policies: Optional[int] = None,
    ) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.status = JobStatus.completed
            rec.completed_at = datetime.now(timezone.utc)
            rec.output_dir = output_dir
            rec.scenarios = scenarios
            rec.output_files = output_files
            rec.total_elapsed_seconds = total_elapsed
            rec.n_policies = n_policies
            if rec.started_at:
                rec.total_elapsed_seconds = (
                    rec.completed_at - rec.started_at
                ).total_seconds()

    def mark_failed(self, job_id: str, error: str) -> None:
        with self._lock:
            rec = self._jobs[job_id]
            rec.status = JobStatus.failed
            rec.completed_at = datetime.now(timezone.utc)
            rec.error = error

    # ------------------------------------------------------------------
    # Read helpers (called from request handlers)
    # ------------------------------------------------------------------

    def get(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def list_ids(self) -> List[str]:
        with self._lock:
            return list(self._jobs.keys())


job_store = JobStore()
