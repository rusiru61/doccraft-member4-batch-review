from datetime import datetime, timezone
from uuid import uuid4

from app.integrations.document_provider import DocumentProvider
from app.repositories import batch_repository as repo
from app.schemas.batch import (
    BatchCreate, BatchDetailResponse, BatchProgress, BatchResponse,
    BatchStatus, ItemStatus, JobItemResponse,
)


class UnknownDocumentError(Exception):
    def __init__(self, document_ids: list[str]):
        self.document_ids = document_ids
        super().__init__(f"Unknown document IDs: {document_ids}")


def build_progress(counts: dict[str, int]) -> BatchProgress:
    total = sum(counts.values())
    finished = counts.get("completed", 0) + counts.get("failed", 0)
    percent = round(finished / total * 100, 1) if total else 0.0
    return BatchProgress(
        total=total,
        pending=counts.get("pending", 0),
        processing=counts.get("processing", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        percent_complete=percent,
    )


def _to_batch_response(batch: dict) -> BatchResponse:
    progress = build_progress(repo.count_by_status(batch["batch_id"]))
    return BatchResponse(**batch, progress=progress)


def create_batch(payload: BatchCreate, provider: DocumentProvider) -> BatchResponse:
    document_ids = list(dict.fromkeys(payload.document_ids))  # remove duplicates, keep order
    documents = {d: provider.get_document(d) for d in document_ids}
    missing = [d for d, doc in documents.items() if doc is None]
    if missing:
        raise UnknownDocumentError(missing)

    now = datetime.now(timezone.utc)
    batch_id = f"BATCH-{uuid4().hex[:8].upper()}"
    batch = {
        "batch_id": batch_id,
        "name": payload.name,
        "priority": payload.priority.value,
        "status": BatchStatus.pending.value,
        "created_at": now,
    }
    items = [
        {
            "item_id": f"{batch_id}-{doc.document_id}",
            "batch_id": batch_id,
            "document_id": doc.document_id,
            "filename": doc.filename,
            "page_count": doc.page_count,
            "text_length": doc.text_length,
            "is_scanned": doc.is_scanned,
            "detected_language": doc.detected_language,
            "status": ItemStatus.pending.value,
            "error_message": None,
            "created_at": now,
        }
        for doc in documents.values()
    ]
    repo.insert_batch(batch, items)
    return _to_batch_response(batch)


def list_batches() -> list[BatchResponse]:
    return [_to_batch_response(b) for b in repo.list_batches()]


def get_batch_detail(batch_id: str) -> BatchDetailResponse | None:
    batch = repo.find_batch(batch_id)
    if batch is None:
        return None
    summary = _to_batch_response(batch)
    items = [JobItemResponse(**i) for i in repo.list_items(batch_id)]
    return BatchDetailResponse(**summary.model_dump(), items=items)