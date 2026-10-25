from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ReviewStatus(str, Enum):
    pending = "pending"
    completed = "completed"


class ReviewTaskResponse(BaseModel):
    task_id: str
    batch_id: str
    item_id: str
    document_id: str
    filename: str
    reliability_score: float
    flagged_fields: list[str]
    status: ReviewStatus
    created_at: datetime