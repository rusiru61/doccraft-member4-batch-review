from datetime import datetime

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    name: str
    value: str | None
    confidence: float = Field(ge=0, le=1)
    found: bool
    required: bool


class ExtractionResult(BaseModel):
    document_id: str
    fields: list[ExtractedField]
    ai_confidence: float = Field(ge=0, le=1)
    validation_passed: bool
    validation_errors: list[str] = []
    extracted_at: datetime