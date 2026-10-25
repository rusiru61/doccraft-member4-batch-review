from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import StringConstraints

from pydantic import BaseModel, Field


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

class FieldCorrection(BaseModel):
    name: str
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class CorrectionRequest(BaseModel):
    corrections: list[FieldCorrection] = Field(min_length=1)


class ReviewFieldView(BaseModel):
    name: str
    original_value: str | None
    current_value: str | None
    confidence: float
    found: bool
    required: bool
    flagged: bool
    corrected: bool


class ReviewTaskDetail(ReviewTaskResponse):
    fields: list[ReviewFieldView]
    validation_errors: list[str]