from datetime import datetime, timezone

from app.integrations.auth_service import CurrentUser
from app.integrations.document_provider import DocumentProvider
from app.repositories import job_repository as repo
from app.schemas.audit import AuditAction
from app.schemas.job import (
    JobCreate, JobDetailResponse, JobProgress, JobResponse,
    JobStatus, ItemStatus, JobItemResponse,
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
        "status": JobStatus.pending.value,
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
        "job",
        job_id,
        job_id,
        {"name": payload.name, "priority": payload.priority.value, "document_count": len(items)},
    )
    return _to_job_response({**job, "job_id": job_id})


def list_jobs() -> list[JobResponse]:
    jobs = repo.list_jobs()
    stats = repo.summarize_items([b["job_id"] for b in jobs]) if jobs else {}
    responses = []
    for job in jobs:
        s = stats.get(job["job_id"], {})
        counts = {k: s.get(k, 0) for k in ("pending", "processing", "completed", "failed")}
        responses.append(JobResponse(**job, progress=build_progress(counts)))
    return responses


def get_job_detail(job_id: str) -> JobDetailResponse | None:
    job = repo.find_job(job_id)
    if job is None:
        return None
    summary = _to_job_response(job)
    items = [JobItemResponse(**i) for i in repo.list_items(job_id)]
    return JobDetailResponse(**summary.model_dump(), items=items)