from datetime import datetime

from pydantic import BaseModel

from app.schemas.batch import BatchStatus, Priority


class JobHistoryEntry(BaseModel):
    batch_id: str
    name: str
    priority: Priority
    status: BatchStatus
    created_by: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    total: int
    completed: int
    failed: int
    pending_review: int


class JobHistoryPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JobHistoryEntry]