from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.routing import LanguageRouting


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    review_required = "review_required"
    completed = "completed"
    partially_failed = "partially_failed"
    failed = "failed"
    cancelled = "cancelled"


class ItemStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    priority: Priority = Priority.medium
    document_ids: list[str] = Field(min_length=1, max_length=500)


class JobItemResponse(BaseModel):
    result_id: str
    job_id: str
    document_id: str
    filename: str
    page_count: int
    text_length: int
    detected_language: str
    status: ItemStatus
    error_message: str | None = None
    created_at: datetime
    processing_order: int | None = None
    reliability_score: float | None = None
    review_status: str | None = None
    language_routing: LanguageRouting | None = None


class JobProgress(BaseModel):
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    percent_complete: float


class JobResponse(BaseModel):
    job_id: str
    name: str
    priority: Priority
    status: JobStatus
    created_at: datetime
    created_by: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    finalized_by: str | None = None
    progress: JobProgress


class JobDetailResponse(JobResponse):
    items: list[JobItemResponse]