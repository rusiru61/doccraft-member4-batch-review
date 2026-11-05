from datetime import datetime, timezone

from app.integrations.auth_service import CurrentUser
from app.integrations.document_provider import DocumentProvider
from app.repositories import job_repository as repo
from app.schemas.audit import AuditAction
from app.schemas.job import (
    ItemStatus, JobCreate, JobDetailResponse, JobItemResponse, JobProgress, JobResponse, JobStatus,
)
from app.services import audit_service


class UnknownDocumentError(Exception):
    def __init__(self, document_ids: list[str]):
        self.document_ids = document_ids
        super().__init__(f"Unknown document IDs: {document_ids}")


def build_progress(counts: dict[str, int]) -> JobProgress:
    total = sum(counts.values())
    finished = counts.get("completed", 0) + counts.get("failed", 0)
    percent = round(finished / total * 100, 1) if total else 0.0
    return JobProgress(
        total=total,
        pending=counts.get("pending", 0),
        processing=counts.get("processing", 0),
        completed=counts.get("completed", 0),
        failed=counts.get("failed", 0),
        percent_complete=percent,
    )


def _to_job_response(job: dict) -> JobResponse:
    progress = build_progress(repo.count_by_status(job["job_id"]))
    return JobResponse(**job, progress=progress)


def create_job(payload: JobCreate, provider: DocumentProvider, user: CurrentUser) -> JobResponse:
    document_ids = list(dict.fromkeys(payload.document_ids))  # remove duplicates, keep order
    documents = {d: provider.get_document(d) for d in document_ids}
    missing = [d for d, doc in documents.items() if doc is None]
    if missing:
        raise UnknownDocumentError(missing)

    now = datetime.now(timezone.utc)
    job = {
        "name": payload.name,
        "priority": payload.priority.value,
        "status": JobStatus.queued.value,
        "created_by": user.user_id,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
    }
    items = [
        {
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
    job_id = repo.insert_job(job, items)
    audit_service.record(
        user.user_id,
        AuditAction.job_created,
        "extraction_job",
        job_id,
        job_id,
        {"name": payload.name, "priority": payload.priority.value, "document_count": len(items)},
    )
    return _to_job_response({**job, "job_id": job_id})


def get_job(job_id: str) -> JobResponse | None:
    job = repo.find_job(job_id)
    return None if job is None else _to_job_response(job)


def get_job_detail(job_id: str) -> JobDetailResponse | None:
    summary = get_job(job_id)
    if summary is None:
        return None
    items = [JobItemResponse(**i) for i in repo.list_items(job_id)]
    return JobDetailResponse(**summary.model_dump(), items=items)