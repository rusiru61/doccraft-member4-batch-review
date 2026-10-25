import logging

from app.integrations.extraction_service import ExtractionError, ExtractionService
from app.repositories import batch_repository as repo

logger = logging.getLogger(__name__)


class BatchNotFoundError(Exception):
    pass


class BatchNotPendingError(Exception):
    pass


def order_items(items: list[dict]) -> list[dict]:
    """Shortest first: fewer pages, then shorter text, then ID for a stable order."""
    return sorted(items, key=lambda i: (i["page_count"], i["text_length"], i["document_id"]))


def start_processing(batch_id: str) -> None:
    if repo.find_batch(batch_id) is None:
        raise BatchNotFoundError(batch_id)
    if not repo.try_mark_batch_processing(batch_id):
        raise BatchNotPendingError(batch_id)


def _mark_failed(item_id: str, message: str) -> None:
    repo.update_item(item_id, {"status": "failed", "error_message": message})


def process_batch(batch_id: str, extractor: ExtractionService) -> None:
    items = order_items(repo.list_items(batch_id))
    logger.info("Batch %s: processing %d items", batch_id, len(items))

    for position, item in enumerate(items, start=1):
        item_id = item["item_id"]
        repo.update_item(item_id, {"status": "processing", "processing_order": position})
        try:
            result = extractor.extract(item["document_id"])
            repo.update_item(item_id, {"status": "completed", "extraction": result.model_dump()})
        except ExtractionError as exc:  # expected kind of failure
            logger.warning("Batch %s: %s failed: %s", batch_id, item["document_id"], exc)
            _mark_failed(item_id, str(exc))
        except Exception:  # deliberate: one document must never stop the others
            logger.exception("Batch %s: unexpected error on %s", batch_id, item["document_id"])
            _mark_failed(item_id, "Unexpected processing error")

    repo.set_batch_status(batch_id, "completed")
    logger.info("Batch %s: finished", batch_id)