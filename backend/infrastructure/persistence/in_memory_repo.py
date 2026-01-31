from threading import Lock
from typing import Dict, Optional

from backend.domain.models import Job


class InMemoryJobRepository:
    """
    Very simple in-memory repository for demo / local development.

    In a real production system, this would be backed by DynamoDB, RDS, etc.
    """

    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}
        self._lock = Lock()

    def save(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)


# Single process-wide instance for this app
job_repository = InMemoryJobRepository()

