from fastapi import APIRouter, Depends, HTTPException

from app.integrations.auth_service import CurrentUser, get_current_user
from app.schemas.review import (
    CorrectionRequest, ReviewStatus, ReviewTaskDetail, ReviewTaskResponse,
)
from app.services import review_service
from app.services.review_service import (
    TaskNotFoundError, TaskNotPendingError, UnknownFieldError,
)

router = APIRouter(prefix="/review-tasks", tags=["review"])


@router.get("", response_model=list[ReviewTaskResponse])
def list_review_tasks(status: ReviewStatus | None = ReviewStatus.pending):
    """The review queue: pending tasks by default, lowest reliability score first."""
    return review_service.list_queue(status)


@router.get("/{task_id}", response_model=ReviewTaskDetail)
def get_review_task(task_id: str):
    try:
        return review_service.get_task_detail(task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Review task not found")


@router.patch("/{task_id}/fields", response_model=ReviewTaskDetail)
def correct_fields(
    task_id: str,
    payload: CorrectionRequest,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return review_service.apply_corrections(task_id, payload, user)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Review task not found")
    except TaskNotPendingError:
        raise HTTPException(status_code=409, detail="Review task is no longer pending")
    except UnknownFieldError as exc:
        raise HTTPException(status_code=422, detail=str(exc))