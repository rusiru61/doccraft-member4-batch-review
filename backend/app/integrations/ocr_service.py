from typing import Protocol


class OcrService(Protocol):
    def get_ocr_confidence(self, document_id: str, is_scanned: bool) -> float | None: ...


_SCAN_SCORES = {"DOC-003": 0.45, "DOC-005": 0.70, "DOC-006": 0.60}
_DEFAULT_SCAN_SCORE = 0.85


class MockOcrService:
    """Fake stand-in for Member 2. Digital documents need no OCR, so they return None."""

    def get_ocr_confidence(self, document_id: str, is_scanned: bool) -> float | None:
        if not is_scanned:
            return None  # contract G2: OCR_status = "not_required"
        return _SCAN_SCORES.get(document_id, _DEFAULT_SCAN_SCORE)


def get_ocr_service() -> OcrService:
    """THE swap point for Member 2's OCR module."""
    return MockOcrService()