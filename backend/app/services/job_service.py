from datetime import datetime, timezone

from app.integrations.auth_service import CurrentUser
from app.integrations.document_provider import DocumentProvider
from app.integrations.mapping_provider import MappingProvider
from app.integrations.template_provider import TemplateProvider
from app.repositories import job_repository as repo
from app.schemas.audit import AuditAction
from app.schemas.configuration import MappingInfo
from app.schemas.job import (
    ItemStatus, JobCreate, JobDetailResponse, JobItemResponse, JobProgress,
    JobResponse, JobResultResponse, JobStatus,
)
from app.services import audit_service


class InvalidJobReferenceError(Exception):
    """A document, template or mapping named in the request cannot be used."""

    def __init__(self, code: str, message: str, conflict: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.conflict = conflict  # True = valid but in the wrong state (409), else invalid (422)


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


def _resolve_mapping(
    template_id: str, mapping_id: str, templates: TemplateProvider, mappings: MappingProvider
) -> MappingInfo:
    template = templates.get_template(template_id)
    if template is None:
        raise InvalidJobReferenceError("TEMPLATE_NOT_FOUND", "The selected template was not found.")
    if not template.is_active:
        raise InvalidJobReferenceError(
            "TEMPLATE_INACTIVE", "The selected template is not active.", conflict=True
        )
    mapping = mappings.get_mapping(mapping_id)
    if mapping is None:
        raise InvalidJobReferenceError("MAPPING_NOT_FOUND", "The selected mapping was not found.")
    if mapping.template_id != template_id:
        raise InvalidJobReferenceError(
            "MAPPING_TEMPLATE_MISMATCH", "The mapping does not belong to the selected template."
        )
    if not mapping.is_active:
        raise InvalidJobReferenceError(
            "MAPPING_INACTIVE", "The selected mapping is not active.", conflict=True
        )
    return mapping


def create_job(
    payload: JobCreate,
    provider: DocumentProvider,
    templates: TemplateProvider,
    mappings: MappingProvider,
    user: CurrentUser,
) -> JobResponse:
    mapping = _resolve_mapping(payload.template_id, payload.mapping_id, templates, mappings)

    document_ids = list(dict.fromkeys(payload.document_ids))  # remove duplicates, keep order
    documents = {d: provider.get_document(d) for d in document_ids}
    missing = [d for d, doc in documents.items() if doc is None]
    if missing:
        raise InvalidJobReferenceError("DOCUMENT_NOT_FOUND", f"Unknown document IDs: {missing}")

    now = datetime.now(timezone.utc)
    job = {
        "name": payload.name or f"Job {now:%Y-%m-%d %H:%M}",
        "priority": payload.priority.value,
        "status": JobStatus.queued.value,
        "template_id": payload.template_id,
        "mapping_id": mapping.mapping_id,
        "mapping_version": mapping.version,
        "data_structure_id": mapping.data_structure_id,
        "created_by": user.user_id,
        "created_at": now,
        "start_requested_at": None,
        "started_at": None,
        "completed_at": None,
    }
    items = [
        {
            "document_id": doc.document_id,
            "template_id": payload.template_id,
            "mapping_id": mapping.mapping_id,
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
        {
            "name": job["name"],
            "priority": payload.priority.value,
            "document_count": len(items),
            "template_id": payload.template_id,
            "mapping_id": mapping.mapping_id,
        },
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


def get_job_results(job_id: str) -> list[JobResultResponse] | None:
    if repo.find_job(job_id) is None:
        return None
    return [JobResultResponse(**i) for i in repo.list_items(job_id)]