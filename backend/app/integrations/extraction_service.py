import time
from datetime import datetime, timezone
from typing import Protocol

from app.core.config import settings
from app.schemas.extraction import ExtractionResult, FieldResult


class ExtractionError(Exception):
    """Raised when a document cannot be extracted. Maps to status 'failed' in the job."""


class ExtractionService(Protocol):
    def extract(self, document_id: str, mapping_id: str | None = None) -> ExtractionResult: ...

# document_id -> (ai_confidence, what happens to the supplier_name field)
_OUTCOMES = {
    "DOC-001": (0.95, "ok"),
    "DOC-002": (0.88, "ok"),
    "DOC-003": (0.55, "missing"),   # blurry receipt
    "DOC-004": (0.91, "ok"),
    "DOC-005": (0.72, "ok"),        # Sinhala scan
    "DOC-006": (0.64, "invalid"),   # Tamil scan
    "DOC-007": (0.93, "ok"),
    "DOC-009": (0.85, "ok"),
    "DOC-010": (0.78, "ok"),
}
_FAILING_IDS = {"DOC-008"}


class MockExtractionService:
    """Fake stand-in for Member 3. Same output for the same document, every run."""

    def extract(self, document_id: str, mapping_id: str | None = None) -> ExtractionResult:
        time.sleep(settings.mock_processing_delay_seconds)
        if document_id in _FAILING_IDS:
            raise ExtractionError("Mock failure: text could not be read from document")

        ai_confidence, supplier = _OUTCOMES.get(document_id, (0.80, "ok"))
        number = f"INV-{document_id[-3:]}"
        field_values = {
            "invoice_number": FieldResult(
                value=number, status="extracted", source_text=f"Invoice No: {number}"
            ),
            "total_amount": FieldResult(
                value="1500.00", status="extracted", source_text="Total: 1,500.00"
            ),
        }
        errors: list[str] = []
        if supplier == "ok":
            field_values["supplier_name"] = FieldResult(
                value="ABC Traders", status="extracted", source_text="Supplier: ABC Traders"
            )
        elif supplier == "missing":
            field_values["supplier_name"] = FieldResult(value=None, status="missing")
            errors.append("Missing supplier name")
        else:
            field_values["supplier_name"] = FieldResult(
                value="???", status="invalid", source_text="Supplier: ???"
            )
            errors.append("Supplier name failed validation")

        return ExtractionResult(
            document_id=document_id,
            field_values=field_values,
            ai_confidence=ai_confidence,
            validation_errors=errors,
            extracted_at=datetime.now(timezone.utc),
        )


def get_extraction_service() -> ExtractionService:
    """THE swap point for Member 3's extraction engine."""
    return MockExtractionService()