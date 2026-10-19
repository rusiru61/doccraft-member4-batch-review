from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

LanguageCode = Literal["en", "si", "ta", "unknown"]


class DocumentInfo(BaseModel):
    document_id: str
    filename: str
    file_type: Literal["pdf", "docx", "image"]
    page_count: int = Field(ge=1)
    text_length: int = Field(ge=0)
    is_scanned: bool
    detected_language: LanguageCode
    upload_timestamp: datetime