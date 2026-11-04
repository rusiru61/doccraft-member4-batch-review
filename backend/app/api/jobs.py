from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.integrations.auth_service import CurrentUser, get_current_user
from app.integrations.document_provider import DocumentProvider, get_document_provider
from app.schemas.job import JobCreate, JobDetailResponse, JobResponse
from app.services import job_service, processing_service
from app.services.job_service import UnknownDocumentError
from app.services.processing_service import (
    JobNotFoundError, JobNotPendingError, QueueUnavailableError,
)
from app.tasks.processing_tasks import enqueue_job_processing

router = APIRouter(prefix="/extraction-jobs", tags=["extraction-jobs"])


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


@router.get("", response_model=list[JobResponse])
def list_jobs():
    return job_service.list_jobs()


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: str):
    job = job_service.get_job_detail(job_id)
    if job is None:
        raise ApiError(404, "JOB_NOT_FOUND", "The requested job was not found.")
    return job


@router.post("/{job_id}/process", status_code=202)
def process_job(job_id: str, user: CurrentUser = Depends(get_current_user)):
    try:
        processing_service.start_processing(job_id, user, enqueue_job_processing)
    except JobNotFoundError:
        raise ApiError(404, "JOB_NOT_FOUND", "The requested job was not found.")
    except JobNotPendingError:
        raise ApiError(409, "JOB_ALREADY_STARTED", "This job has already been started.")
    except QueueUnavailableError:
        raise ApiError(503, "QUEUE_UNAVAILABLE", "The job queue is unavailable, please try again.")
    return {"job_id": job_id, "status": "processing"}