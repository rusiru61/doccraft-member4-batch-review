from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# What the extraction engine may return. "corrected" is set only by a human reviewer.
EngineFieldStatus = Literal["extracted", "missing", "invalid"]


class FieldResult(BaseModel):
    value: str | None
    status: EngineFieldStatus
    source_text: str | None = None


class ExtractionResult(BaseModel):
    document_id: str
    field_values: dict[str, FieldResult]
    ai_confidence: float | None = Field(default=None, ge=0, le=1)  # optional, not calibrated
    validation_errors: list[str] = []
    extracted_at: datetime