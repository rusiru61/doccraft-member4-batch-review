from fastapi import APIRouter, Depends, HTTPException

from app.integrations.document_provider import DocumentProvider, get_document_provider
from app.schemas.batch import BatchCreate, BatchDetailResponse, BatchResponse
from app.services import batch_service
from app.services.batch_service import UnknownDocumentError

router = APIRouter(prefix="/batches", tags=["batches"])


@router.post("", response_model=BatchResponse, status_code=201)
def create_batch(
    payload: BatchCreate,
    provider: DocumentProvider = Depends(get_document_provider),
):
    try:
        return batch_service.create_batch(payload, provider)
    except UnknownDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("", response_model=list[BatchResponse])
def list_batches():
    return batch_service.list_batches()


@router.get("/{batch_id}", response_model=BatchDetailResponse)
def get_batch(batch_id: str):
    batch = batch_service.get_batch_detail(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch