"""
In-memory job store for async CSV import jobs.
Each job has: status, progress, message, result.
Jobs are stored in a simple dict — lost on server restart (acceptable for demo).
"""
import threading
import uuid
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from core.logger import get_logger

logger = get_logger(__name__)

@dataclass
class ImportJob:
    job_id: str
    status: str = "queued"          # queued | compressing | parsing | sorting | copying | done | failed
    progress: int = 0               # 0-100
    message: str = "Queued"
    imported: int = 0
    errors: int = 0
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    finished_at: Optional[str] = None

_store: dict[str, ImportJob] = {}
_lock = threading.Lock()


def create_job() -> ImportJob:
    job_id = str(uuid.uuid4())[:8]
    job = ImportJob(job_id=job_id)
    with _lock:
        _store[job_id] = job
    logger.debug("job_store | Created job | job_id=%s", job_id)
    return job


def update_job(job_id: str, **kwargs):
    with _lock:
        job = _store.get(job_id)
        if not job:
            logger.warning("job_store | Job not found | job_id=%s", job_id)
            return
        for k, v in kwargs.items():
            setattr(job, k, v)
        if kwargs.get("status") in ("done", "failed"):
            job.finished_at = datetime.utcnow().isoformat()
    logger.debug("job_store | Updated job | job_id=%s status=%s progress=%s",
                 job_id, kwargs.get("status", "?"), kwargs.get("progress", "?"))


def get_job(job_id: str) -> Optional[ImportJob]:
    with _lock:
        return _store.get(job_id)
