from pydantic import BaseModel


class LanguageRouting(BaseModel):
    language: str
    pipeline: str
    ocr_language: str
    requires_review: bool