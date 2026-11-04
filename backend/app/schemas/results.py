from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FinalField(BaseModel):
    field_id: str
    name: str
    value: str | None
    status: str  # extracted, missing, invalid, or corrected

class FinalizedResult(BaseModel):
    result_id: str
    job_id: str
    document_id: str
    filename: str
    reliability_score: float
    review_status: Literal["not_required", "approved"]
    finalized_by: str
    finalized_at: datetime
    fields: list[FinalField]