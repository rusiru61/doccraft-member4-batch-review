import logging

from kombu.exceptions import OperationalError

from app.core.celery_app import celery_app
from app.integrations.extraction_service import get_extraction_service
from app.integrations.ocr_service import get_ocr_service
from app.services import processing_service
from app.services.processing_service import QueueUnavailableError

logger = logging.getLogger(__name__)


@celery_app.task(name="batches.process")
def run_batch_processing(batch_id: str) -> None:
    """Runs in the worker. Receives only an ID and builds its own services."""
    processing_service.process_batch(batch_id, get_extraction_service(), get_ocr_service())


def enqueue_batch_processing(batch_id: str) -> None:
    """Called by the API. Turns a broker failure into our own error type."""
    try:
        run_batch_processing.delay(batch_id)
    except OperationalError as exc:
        logger.error("Job queue unavailable while enqueuing batch %s", batch_id)
        raise QueueUnavailableError(batch_id) from exc