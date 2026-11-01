from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.integrations.auth_service import CurrentUser, get_current_user
from app.integrations.document_provider import DocumentProvider, get_document_provider
from app.schemas.batch import BatchCreate, BatchDetailResponse, BatchResponse
from app.services import batch_service, processing_service
from app.services.batch_service import UnknownDocumentError
from app.services.processing_service import (
    BatchNotFoundError, BatchNotPendingError, QueueUnavailableError,
)
from app.tasks.processing_tasks import enqueue_batch_processing

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("", response_model=BatchResponse, status_code=201)
def create_batch(
    payload: BatchCreate,
    provider: DocumentProvider = Depends(get_document_provider),
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return batch_service.create_batch(payload, provider, user)
    except UnknownDocumentError as exc:
        raise ApiError(422, "DOCUMENT_NOT_FOUND", str(exc))


@router.get("", response_model=list[BatchResponse])
def list_batches():
    return batch_service.list_batches()


@router.get("/{batch_id}", response_model=BatchDetailResponse)
def get_batch(batch_id: str):
    batch = batch_service.get_batch_detail(batch_id)
    if batch is None:
        raise ApiError(404, "JOB_NOT_FOUND", "The requested job was not found.")
    return batch


@router.post("/{batch_id}/process", status_code=202)
def process_batch(batch_id: str, user: CurrentUser = Depends(get_current_user)):
    try:
        processing_service.start_processing(batch_id, user, enqueue_batch_processing)
    except BatchNotFoundError:
        raise ApiError(404, "JOB_NOT_FOUND", "The requested job was not found.")
    except BatchNotPendingError:
        raise ApiError(409, "JOB_ALREADY_STARTED", "This job has already been started.")
    except QueueUnavailableError:
        raise ApiError(503, "QUEUE_UNAVAILABLE", "The job queue is unavailable, please try again.")
    return {"batch_id": batch_id, "status": "processing"}