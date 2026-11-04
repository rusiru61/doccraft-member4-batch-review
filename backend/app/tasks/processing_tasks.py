import logging

from kombu.exceptions import OperationalError
from app.integrations.data_structure_provider import get_data_structure_provider

from app.core.celery_app import celery_app, queue_for_priority
from app.integrations.extraction_service import get_extraction_service
from app.integrations.ocr_service import get_ocr_service
from app.services import processing_service
from app.services.processing_service import QueueUnavailableError

logger = logging.getLogger(__name__)


@celery_app.task(name="jobs.process")
def run_job_processing(job_id: str) -> None:
    """Runs in the worker. Receives only an ID and builds its own services."""
    processing_service.process_job(
        job_id, get_extraction_service(), get_ocr_service(), get_data_structure_provider()
    )


def enqueue_job_processing(job_id: str, priority: str) -> None:
    """Called by the API. Sends the job to the queue that matches its priority."""
    try:
        run_job_processing.apply_async(args=[job_id], queue=queue_for_priority(priority))
    except OperationalError as exc:
        logger.error("Job queue unavailable while enqueuing job %s", job_id)
        raise QueueUnavailableError(job_id) from exc