from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FinalField(BaseModel):
    name: str
    value: str | None
    corrected: bool


class FinalizedResult(BaseModel):
    item_id: str
    batch_id: str
    document_id: str
    filename: str
    reliability_score: float
    review_status: Literal["not_required", "approved"]
    finalized_by: str
    finalized_at: datetime
    fields: list[FinalField]