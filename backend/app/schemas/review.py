from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class ReviewStatus(str, Enum):
    pending_review = "pending_review"
    approved = "approved"
    not_required = "not_required"


class FieldCorrection(BaseModel):
    field_id: str
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class CorrectionRequest(BaseModel):
    corrections: list[FieldCorrection] = Field(min_length=1)


class ResultSummary(BaseModel):
    result_id: str
    job_id: str
    document_id: str
    filename: str
    review_status: ReviewStatus
    reliability_score: float
    review_reasons: list[str] = []
    flagged_fields: list[str] = []
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


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


class ResultDetail(ResultSummary):
    fields: list[ReviewFieldView]
    validation_errors: list[str]