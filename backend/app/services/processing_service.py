import logging
from typing import Callable

from app.integrations.auth_service import CurrentUser
from app.integrations.data_structure_provider import (
    DataStructureProvider, get_data_structure_provider,
)
from app.integrations.extraction_service import ExtractionError, ExtractionService
from app.integrations.ocr_service import OcrService
from app.repositories import batch_repository as repo
from app.schemas.audit import AuditAction
from app.services import audit_service, extraction_rules, review_service, routing_service
from app.services.reliability_service import calculate_reliability_score

logger = logging.getLogger(__name__)


class BatchNotFoundError(Exception):
    pass


class BatchNotPendingError(Exception):
    pass


class QueueUnavailableError(Exception):
    pass


def order_items(items: list[dict]) -> list[dict]:
    """Shortest first: fewer pages, then shorter text, then ID for a stable order."""
    return sorted(items, key=lambda i: (i["page_count"], i["text_length"], i["document_id"]))


def start_processing(
    batch_id: str, user: CurrentUser, enqueue: Callable[[str, str], None]
) -> None:
    batch = repo.find_batch(batch_id)
    if batch is None:
        raise BatchNotFoundError(batch_id)
    if not repo.try_mark_batch_processing(batch_id):
        raise BatchNotPendingError(batch_id)
    try:
        enqueue(batch_id, batch["priority"])
    except QueueUnavailableError:
        repo.revert_batch_to_pending(batch_id)  # nothing was queued, so undo the mark
        raise
    # The audit entry is written only after the job is really queued.
    audit_service.record(
        user.user_id, AuditAction.processing_started, "batch", batch_id, batch_id
    )


def _mark_failed(item_id: str, message: str) -> None:
    repo.update_item(item_id, {"status": "failed", "error_message": message})


def process_batch(
    batch_id: str,
    extractor: ExtractionService,
    ocr_service: OcrService,
    structure_provider: DataStructureProvider | None = None,
) -> None:
    repo.mark_batch_started(batch_id)
    # Snapshot the field definitions once per run, so review never depends on a live lookup.
    definitions = (structure_provider or get_data_structure_provider()).get_field_definitions()
    definition_snapshot = [d.model_dump() for d in definitions]

    items = order_items(repo.list_items(batch_id))
    remaining = sum(1 for i in items if i["status"] in ("pending", "processing"))
    logger.info("Batch %s: processing %d of %d items", batch_id, remaining, len(items))

    for position, item in enumerate(items, start=1):
        if item["status"] in ("completed", "failed"):
            continue  # finished before a restart or redelivery, so never redo it
        item_id = item["item_id"]
        routing = routing_service.route_language(item["detected_language"])
        repo.update_item(
            item_id,
            {
                "status": "processing",
                "processing_order": position,
                "language_routing": routing.model_dump(),
            },
        )
        try:
            result = extractor.extract(item["document_id"])
            extracted = result.model_dump()
            ocr = ocr_service.get_ocr_confidence(item["document_id"], item.get("is_scanned", False))
            problems = extraction_rules.find_required_problems(extracted["field_values"], definitions)
            score = calculate_reliability_score(
                ocr, result.ai_confidence, validation_passed=not problems
            )
            decision = review_service.decide_review(
                result, definitions, score, force_review=routing.requires_review
            )
            # ONE write: the extraction and its review decision are saved together or not at all.
            repo.update_item(
                item_id,
                {
                    "status": "completed",
                    "field_values": extracted["field_values"],
                    "ai_confidence": extracted["ai_confidence"],
                    "validation_errors": extracted["validation_errors"],
                    "extracted_at": extracted["extracted_at"],
                    "field_definitions": definition_snapshot,
                    "ocr_confidence": ocr,
                    "reliability_score": score,
                    **decision,
                },
            )
        except ExtractionError as exc:  # expected kind of failure
            logger.warning("Batch %s: %s failed: %s", batch_id, item["document_id"], exc)
            _mark_failed(item_id, str(exc))
        except Exception:  # deliberate: one document must never stop the others
            logger.exception("Batch %s: unexpected error on %s", batch_id, item["document_id"])
            _mark_failed(item_id, "Unexpected processing error")

    repo.set_batch_status(batch_id, "completed")
    logger.info("Batch %s: finished", batch_id)