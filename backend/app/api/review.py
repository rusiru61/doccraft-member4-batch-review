from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.integrations.auth_service import CurrentUser, get_current_user
from app.schemas.review import (
    CorrectionRequest, ReviewStatus, ReviewTaskDetail, ReviewTaskResponse,
)
from app.services import review_service
from app.services.review_service import (
    MissingRequiredFieldsError, TaskNotFoundError, TaskNotPendingError, UnknownFieldError,
)

router = APIRouter(prefix="/review-tasks", tags=["review"])


def _not_found() -> ApiError:
    return ApiError(404, "RESULT_NOT_FOUND", "The requested review item was not found.")


def _not_pending() -> ApiError:
    return ApiError(409, "REVIEW_NOT_PENDING", "This review item is no longer pending.")


@router.get("", response_model=list[ReviewTaskResponse])
def list_review_tasks(status: ReviewStatus | None = ReviewStatus.pending):
    """The review queue: pending tasks by default, lowest reliability score first."""
    return review_service.list_queue(status)


@router.get("/{task_id}", response_model=ReviewTaskDetail)
def get_review_task(task_id: str):
    try:
        return review_service.get_task_detail(task_id)
    except TaskNotFoundError:
        raise _not_found()


@router.patch("/{task_id}/fields", response_model=ReviewTaskDetail)
def correct_fields(
    task_id: str,
    payload: CorrectionRequest,
    user: CurrentUser = Depends(get_current_user),
):
    try:
        return review_service.apply_corrections(task_id, payload, user)
    except TaskNotFoundError:
        raise _not_found()
    except TaskNotPendingError:
        raise _not_pending()
    except UnknownFieldError as exc:
        raise ApiError(422, "UNKNOWN_FIELD", str(exc))


@router.post("/{task_id}/finalize", response_model=ReviewTaskDetail)
def finalize_task(task_id: str, user: CurrentUser = Depends(get_current_user)):
    try:
        return review_service.finalize_task(task_id, user)
    except TaskNotFoundError:
        raise _not_found()
    except TaskNotPendingError:
        raise _not_pending()
    except MissingRequiredFieldsError as exc:
        raise ApiError(422, "REQUIRED_FIELDS_MISSING", str(exc))