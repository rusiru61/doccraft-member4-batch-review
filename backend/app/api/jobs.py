from fastapi import APIRouter, Depends, Query

from app.core.errors import ApiError
from app.integrations.auth_service import CurrentUser, get_current_user
from app.integrations.document_provider import DocumentProvider, get_document_provider
from app.integrations.output_service import OutputService, get_output_service
from app.schemas.history import JobHistoryPage
from app.schemas.job import JobCreate, JobDetailResponse, JobResponse, JobStatus
from app.services import finalize_service, history_service, job_service, processing_service
from app.services.finalize_service import JobNotFinalizableError, ReviewsPendingError
from app.services.job_service import UnknownDocumentError
from app.services.processing_service import (
    JobNotFoundError, JobNotPendingError, QueueUnavailableError,
)
from app.tasks.processing_tasks import enqueue_job_processing

router = APIRouter(prefix="/extraction-jobs", tags=["extraction-jobs"])


def _not_found() -> ApiError:
    return ApiError(404, "JOB_NOT_FOUND", "The requested job was not found.")


@router.post("", response_model=JobResponse, status_code=201)
def create_job(
    payload: JobCreate,
    provider: DocumentProvider = Depends(get_document_provider),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return job_service.create_job(payload, provider, user)
    except UnknownDocumentError as exc:
        raise ApiError(422, "DOCUMENT_NOT_FOUND", str(exc))


@router.get("", response_model=JobHistoryPage)
def list_jobs(
    status: JobStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Past and current jobs, newest first. This is the job history."""
    return history_service.get_history(status, page, page_size)


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: str):
    job = job_service.get_job_detail(job_id)
    if job is None:
        raise _not_found()
    return job


@router.post("/{job_id}/process", status_code=202)
def process_job(job_id: str, user: CurrentUser = Depends(get_current_user)):
    try:
        processing_service.start_processing(job_id, user, enqueue_job_processing)
    except JobNotFoundError:
        raise _not_found()
    except JobNotPendingError:
        raise ApiError(409, "JOB_ALREADY_STARTED", "This job has already been started.")
    except QueueUnavailableError:
        raise ApiError(503, "QUEUE_UNAVAILABLE", "The job queue is unavailable, please try again.")
    return {"job_id": job_id, "status": "processing"}


@router.post("/{job_id}/finalize", response_model=JobResponse)
def finalize_job(
    job_id: str,
    user: CurrentUser = Depends(get_current_user),
    output_service: OutputService = Depends(get_output_service),
):
    """Close the job once every result has been reviewed, then request delivery."""
    try:
        return finalize_service.finalize_job(job_id, user, output_service)
    except JobNotFoundError:
        raise _not_found()
    except ReviewsPendingError as exc:
        raise ApiError(409, "REVIEWS_PENDING", f"{exc.count} result(s) still need review.")
    except JobNotFinalizableError as exc:
        raise ApiError(
            409, "JOB_NOT_FINALIZABLE", f"A job in status '{exc.status}' cannot be finalized."
        )