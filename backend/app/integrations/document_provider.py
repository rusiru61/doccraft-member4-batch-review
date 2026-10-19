from datetime import datetime, timezone
from typing import Protocol

from app.schemas.document import DocumentInfo


class DocumentProvider(Protocol):
    def list_documents(self) -> list[DocumentInfo]: ...
    def get_document(self, document_id: str) -> DocumentInfo | None: ...


# (id, filename, type, pages, text_length, scanned, language)
_SAMPLE_ROWS = [
    ("DOC-001", "invoice_001.pdf", "pdf", 2, 3100, False, "en"),
    ("DOC-002", "invoice_002.pdf", "pdf", 20, 52000, False, "en"),
    ("DOC-003", "receipt_003.jpg", "image", 1, 600, True, "en"),
    ("DOC-004", "contract_004.pdf", "pdf", 8, 21000, False, "en"),
    ("DOC-005", "sinhala_bill_005.pdf", "pdf", 3, 4200, True, "si"),
    ("DOC-006", "tamil_form_006.pdf", "pdf", 5, 7800, True, "ta"),
    ("DOC-007", "report_007.docx", "docx", 12, 30000, False, "en"),
    ("DOC-008", "scan_008.jpg", "image", 1, 150, True, "unknown"),
    ("DOC-009", "order_009.pdf", "pdf", 4, 9500, False, "en"),
    ("DOC-010", "sinhala_letter_010.docx", "docx", 2, 2500, False, "si"),
]
_FIXED_TIME = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)


class MockDocumentProvider:
    """Fake stand-in for Member 1. Same data on every run (deterministic)."""

    def __init__(self) -> None:
        self._documents = {
            row[0]: DocumentInfo(
                document_id=row[0], filename=row[1], file_type=row[2],
                page_count=row[3], text_length=row[4], is_scanned=row[5],
                detected_language=row[6], upload_timestamp=_FIXED_TIME,
            )
            for row in _SAMPLE_ROWS
        }

    def list_documents(self) -> list[DocumentInfo]:
        return list(self._documents.values())

    def get_document(self, document_id: str) -> DocumentInfo | None:
        return self._documents.get(document_id)


def get_document_provider() -> DocumentProvider:
    """THE swap point. When Member 1's module is ready, change only this."""
    return MockDocumentProvider()