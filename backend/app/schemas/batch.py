from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class BatchStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"


class ItemStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class BatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    priority: Priority = Priority.medium
    document_ids: list[str] = Field(min_length=1, max_length=500)


class JobItemResponse(BaseModel):
    item_id: str
    batch_id: str
    document_id: str
    filename: str
    page_count: int
    text_length: int
    detected_language: str
    status: ItemStatus
    error_message: str | None = None
    processing_order: int | None = None
    created_at: datetime


class BatchProgress(BaseModel):
    total: int
    pending: int
    processing: int
    completed: int
    failed: int
    percent_complete: float


class BatchResponse(BaseModel):
    batch_id: str
    name: str
    priority: Priority
    status: BatchStatus
    created_at: datetime
    progress: BatchProgress


class BatchDetailResponse(BatchResponse):
    items: list[JobItemResponse]