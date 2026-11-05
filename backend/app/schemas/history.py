from datetime import datetime

from pydantic import BaseModel

from app.schemas.job import JobStatus, Priority


class JobHistoryEntry(BaseModel):
    job_id: str
    name: str
    priority: Priority
    status: JobStatus
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    total: int
    completed: int
    failed: int
    pending_review: int
    percent_complete: float


class JobHistoryPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[JobHistoryEntry]