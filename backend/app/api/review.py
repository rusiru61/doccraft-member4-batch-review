from fastapi import APIRouter

from app.schemas.review import ReviewStatus, ReviewTaskResponse
from app.services import review_service

router = APIRouter(prefix="/review-tasks", tags=["review"])


@router.get("", response_model=list[ReviewTaskResponse])
def list_review_tasks(status: ReviewStatus | None = ReviewStatus.pending):
    """The review queue: pending tasks by default, lowest reliability score first."""
    return review_service.list_queue(status)