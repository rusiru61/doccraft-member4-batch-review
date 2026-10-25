from datetime import datetime, timezone

from app.core.config import settings
from app.repositories import review_repository as repo
from app.schemas.extraction import ExtractionResult
from app.schemas.review import ReviewStatus, ReviewTaskResponse


def needs_review(score: float) -> bool:
    """A score exactly equal to the threshold passes (US-06 AC2)."""
    return score < settings.reliability_threshold


def find_flagged_fields(result: ExtractionResult) -> list[str]:
    threshold = settings.reliability_threshold
    return [f.name for f in result.fields if not f.found or f.confidence < threshold]


def flag_if_needed(item: dict, result: ExtractionResult, score: float) -> bool:
    if not needs_review(score):
        return False
    repo.upsert_task(
        {
            "task_id": f"REV-{item['item_id']}",
            "batch_id": item["batch_id"],
            "item_id": item["item_id"],
            "document_id": item["document_id"],
            "filename": item["filename"],
            "reliability_score": score,
            "flagged_fields": find_flagged_fields(result),
            "status": ReviewStatus.pending.value,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return True


def list_queue(status: ReviewStatus | None) -> list[ReviewTaskResponse]:
    value = status.value if status else None
    return [ReviewTaskResponse(**t) for t in repo.list_tasks(value)]