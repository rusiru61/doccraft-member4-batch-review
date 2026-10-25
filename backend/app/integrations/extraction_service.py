import time
from datetime import datetime, timezone
from typing import Protocol

from app.core.config import settings
from app.schemas.extraction import ExtractedField, ExtractionResult


class ExtractionError(Exception):
    """Raised when a document cannot be extracted. Maps to status 'failed' in contract G3."""


class ExtractionService(Protocol):
    def extract(self, document_id: str) -> ExtractionResult: ...


# document_id -> (ai_confidence, validation_passed)
_OUTCOMES = {
    "DOC-001": (0.95, True),
    "DOC-002": (0.88, True),
    "DOC-003": (0.55, False),  # blurry receipt
    "DOC-004": (0.91, True),
    "DOC-005": (0.72, True),   # Sinhala scan
    "DOC-006": (0.64, False),  # Tamil scan
    "DOC-007": (0.93, True),
    "DOC-009": (0.85, True),
    "DOC-010": (0.78, True),
}
_FAILING_IDS = {"DOC-008"}


class MockExtractionService:
    """Fake stand-in for Member 3. Same output for the same document, every run."""

    def extract(self, document_id: str) -> ExtractionResult:
        time.sleep(settings.mock_processing_delay_seconds)
        if document_id in _FAILING_IDS:
            raise ExtractionError("Mock failure: text could not be read from document")

        ai_confidence, valid = _OUTCOMES.get(document_id, (0.80, True))
        fields = [
            ExtractedField(name="invoice_no", value=f"INV-{document_id[-3:]}",
                           confidence=ai_confidence, found=True, required=True),
            ExtractedField(name="total_amount", value="1500.00",
                           confidence=ai_confidence, found=True, required=True),
        ]
        errors: list[str] = []
        if valid:
            fields.append(ExtractedField(name="supplier_name", value="ABC Traders",
                                         confidence=ai_confidence, found=True, required=True))
        else:
            fields.append(ExtractedField(name="supplier_name", value=None,
                                         confidence=0.0, found=False, required=True))
            errors.append("Missing supplier name")

        return ExtractionResult(
            document_id=document_id,
            fields=fields,
            ai_confidence=ai_confidence,
            validation_passed=valid,
            validation_errors=errors,
            extracted_at=datetime.now(timezone.utc),
        )


def get_extraction_service() -> ExtractionService:
    """THE swap point for Member 3's extraction engine."""
    return MockExtractionService()