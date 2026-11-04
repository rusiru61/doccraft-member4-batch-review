from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import StringConstraints

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    pending = "pending"
    approved = "approved"


class ReviewTaskResponse(BaseModel):
    result_id: str
    job_id: str
    result_id: str
    document_id: str
    filename: str
    reliability_score: float
    flagged_fields: list[str]
    status: ReviewStatus
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    review_reasons: list[str] = []

class FieldCorrection(BaseModel):
    field_id: str
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

class CorrectionRequest(BaseModel):
    corrections: list[FieldCorrection] = Field(min_length=1)


class ReviewFieldView(BaseModel):
    field_id: str
    name: str
    type: str
    required: bool
    original_value: str | None
    current_value: str | None
    status: str  # extracted, missing, invalid, or corrected
    source_text: str | None
    flagged: bool


class ReviewTaskDetail(ReviewTaskResponse):
    fields: list[ReviewFieldView]
    validation_errors: list[str]