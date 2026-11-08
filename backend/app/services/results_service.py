from app.repositories import job_repository
from app.schemas.results import FinalizedResult


def list_finalized(job_id: str | None, created_by: str | None = None) -> list[FinalizedResult]:
    return [
        FinalizedResult(
            result_id=r["result_id"],
            job_id=r["job_id"],
            document_id=r["document_id"],
            filename=r["filename"],
            reliability_score=r["reliability_score"],
            review_status=r["review_status"],
            finalized_by=r["finalized_by"],
            finalized_at=r["finalized_at"],
            fields=r["final_fields"],
        )
        for r in job_repository.list_finalized(job_id, created_by)
    ]