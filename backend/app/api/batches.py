from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.integrations.extraction_service import ExtractionService, get_extraction_service
from app.integrations.document_provider import DocumentProvider, get_document_provider
from app.schemas.batch import BatchCreate, BatchDetailResponse, BatchResponse
from app.services import batch_service
from app.services import processing_service
from app.services.batch_service import UnknownDocumentError
from app.services.processing_service import BatchNotFoundError, BatchNotPendingError
from app.integrations.ocr_service import OcrService, get_ocr_service

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

@router.post("/{batch_id}/process", status_code=202)
def process_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    extractor: ExtractionService = Depends(get_extraction_service),
    ocr_service: OcrService = Depends(get_ocr_service),
):
    try:
        processing_service.start_processing(batch_id)
    except BatchNotFoundError:
        raise HTTPException(status_code=404, detail="Batch not found")
    except BatchNotPendingError:
        raise HTTPException(status_code=409, detail="Batch has already been started")
    background_tasks.add_task(processing_service.process_batch, batch_id, extractor, ocr_service)
    return {"batch_id": batch_id, "status": "processing"}