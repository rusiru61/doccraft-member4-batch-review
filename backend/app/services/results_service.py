from app.repositories import job_repository
from app.schemas.results import FinalizedResult


def list_finalized(job_id: str | None) -> list[FinalizedResult]:
    return [
        FinalizedResult(
            result_id=i["result_id"],
            job_id=i["job_id"],
            document_id=i["document_id"],
            filename=i["filename"],
            reliability_score=i["reliability_score"],
            review_status=i["review_status"],
            finalized_by=i["finalized_by"],
            finalized_at=i["finalized_at"],
            fields=i["final_fields"],
        )
        for i in job_repository.list_finalized(job_id)
    ]