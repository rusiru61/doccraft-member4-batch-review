import logging
from datetime import datetime, timezone

from app.integrations.auth_service import CurrentUser
from app.integrations.output_service import OutputService
from app.repositories import job_repository as repo
from app.schemas.audit import AuditAction
from app.schemas.job import JobResponse
from app.services import audit_service, job_service
from app.services.processing_service import JobNotFoundError

logger = logging.getLogger(__name__)


class JobNotFinalizableError(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(f"Job in status '{status}' cannot be finalized")


class ReviewsPendingError(Exception):
    def __init__(self, count: int):
        self.count = count
        super().__init__(f"{count} result(s) still need review")


def finalize_job(job_id: str, user: CurrentUser, output_service: OutputService) -> JobResponse:
    job = repo.find_job(job_id)
    if job is None:
        raise JobNotFoundError(job_id)
    if job["status"] != "review_required":
        raise JobNotFinalizableError(job["status"])
    pending = repo.count_pending_review(job_id)
    if pending:
        raise ReviewsPendingError(pending)

    counts = repo.count_by_status(job_id)
    final_status = "partially_failed" if counts.get("failed", 0) else "completed"
    if not repo.try_finalize_job(job_id, final_status, user.user_id, datetime.now(timezone.utc)):
        raise JobNotFinalizableError("already finalized")  # someone else finalized first

    audit_service.record(
        user.user_id,
        AuditAction.job_finalized,
        "extraction_job",
        job_id,
        job_id,
        {"status": final_status, "document_count": sum(counts.values())},
    )
    try:
        output_service.deliver(job_id)
    except Exception:
        # Delivery status is separate from extraction: a failed delivery never undoes finalization.
        logger.exception("Delivery request failed for job %s; results are kept", job_id)
    return job_service.get_job(job_id)