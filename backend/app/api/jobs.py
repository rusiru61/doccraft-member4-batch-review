from fastapi import APIRouter, Depends, Query, Response

from app.core.errors import ApiError
from app.integrations.auth_service import CurrentUser, require_roles
from app.integrations.document_provider import DocumentProvider, get_document_provider
from app.integrations.mapping_provider import MappingProvider, get_mapping_provider
from app.integrations.output_service import OutputService, get_output_service
from app.integrations.template_provider import TemplateProvider, get_template_provider
from app.schemas.history import JobHistoryPage
from app.schemas.job import (
    JobCreate, JobDetailResponse, JobResponse, JobResultResponse, JobStatus,
)
from app.services import (
    finalize_service, history_service, job_service, permissions, processing_service,
)
from app.services.finalize_service import JobNotFinalizableError, ReviewsPendingError
from app.services.job_service import InvalidJobReferenceError
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
    response: Response,
    provider: DocumentProvider = Depends(get_document_provider),
    templates: TemplateProvider = Depends(get_template_provider),
    mappings: MappingProvider = Depends(get_mapping_provider),
    user: CurrentUser = Depends(require_roles(*permissions.CREATE_JOBS)),
):
    """Create a job. By default it is queued for processing right away (202).
    With start=false it is only created (201) and can be started later."""
    try:
        job = job_service.create_job(payload, provider, templates, mappings, user)
    except InvalidJobReferenceError as exc:
        raise ApiError(409 if exc.conflict else 422, exc.code, exc.message)

    if payload.start:
        try:
            processing_service.start_processing(job.job_id, user, enqueue_job_processing)
        except QueueUnavailableError:
            raise ApiError(
                503,
                "QUEUE_UNAVAILABLE",
                f"The job was created ({job.job_id}) but could not be queued. "
                f"Start it later with POST /api/v1/extraction-jobs/{job.job_id}/process.",
            )
        response.status_code = 202
    return job


@router.get("", response_model=JobHistoryPage)
def list_jobs(
    status: JobStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(require_roles(*permissions.VIEW_RESULTS)),
):
    """Your jobs, newest first (admins see everyone's). This is the job history."""
    return history_service.get_history(status, page, page_size, permissions.owner_scope(user))


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(
    job_id: str, user: CurrentUser = Depends(require_roles(*permissions.VIEW_RESULTS))
):
    job = job_service.get_job_detail(job_id, user)
    if job is None:
        raise _not_found()
    return job


@router.get("/{job_id}/results", response_model=list[JobResultResponse])
def get_job_results(
    job_id: str, user: CurrentUser = Depends(require_roles(*permissions.VIEW_RESULTS))
):
    results = job_service.get_job_results(job_id, user)
    if results is None:
        raise _not_found()
    return results


@router.post("/{job_id}/process", status_code=202)
def process_job(
    job_id: str, user: CurrentUser = Depends(require_roles(*permissions.CREATE_JOBS))
):
    """Start a job that was created with start=false."""
    try:
        processing_service.start_processing(job_id, user, enqueue_job_processing)
    except JobNotFoundError:
        raise _not_found()
    except JobNotPendingError:
        raise ApiError(409, "JOB_ALREADY_STARTED", "This job has already been started.")
    except QueueUnavailableError:
        raise ApiError(503, "QUEUE_UNAVAILABLE", "The job queue is unavailable, please try again.")
    return {"job_id": job_id, "status": "queued"}


@router.post("/{job_id}/finalize", response_model=JobResponse)
def finalize_job(
    job_id: str,
    user: CurrentUser = Depends(require_roles(*permissions.FINALIZE)),
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