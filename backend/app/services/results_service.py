from app.repositories import batch_repository
from app.schemas.results import FinalizedResult


def list_finalized(batch_id: str | None) -> list[FinalizedResult]:
    return [
        FinalizedResult(
            item_id=i["item_id"],
            batch_id=i["batch_id"],
            document_id=i["document_id"],
            filename=i["filename"],
            reliability_score=i["reliability_score"],
            review_status=i["review_status"],
            finalized_by=i["finalized_by"],
            finalized_at=i["finalized_at"],
            fields=i["final_fields"],
        )
        for i in batch_repository.list_finalized(batch_id)
    ]