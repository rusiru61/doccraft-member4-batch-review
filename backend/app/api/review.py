from fastapi import APIRouter, Depends

from app.core.errors import ApiError
from app.integrations.auth_service import CurrentUser, get_current_user
from app.schemas.review import CorrectionRequest, ResultDetail, ResultSummary, ReviewStatus
from app.services import review_service
from app.services.review_service import (
    MissingRequiredFieldsError, ResultNotFoundError, ReviewNotPendingError, UnknownFieldError,
)

router = APIRouter(prefix="/extraction-results", tags=["extraction-results"])


def _not_found() -> ApiError:
    return ApiError(404, "RESULT_NOT_FOUND", "The requested result was not found.")


def _not_pending() -> ApiError:
    return ApiError(409, "REVIEW_NOT_PENDING", "This result is not waiting for review.")


@router.get("", response_model=list[ResultSummary])
def list_results(
    review_status: ReviewStatus = ReviewStatus.pending_review,
    job_id: str | None = None,
):
    """By default the review queue: results waiting for review, lowest reliability score first."""
    return review_service.list_results(review_status, job_id)


@router.get("/{result_id}", response_model=ResultDetail)
def get_result(result_id: str):
    try:
        return review_service.get_result_detail(result_id)
    except ResultNotFoundError:
        raise _not_found()


@router.patch("/{result_id}", response_model=ResultDetail)
def correct_result(
    result_id: str,
    payload: CorrectionRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Save manual corrections before the result is approved."""
    try:
        return review_service.apply_corrections(result_id, payload, user)
    except ResultNotFoundError:
        raise _not_found()
    except ReviewNotPendingError:
        raise _not_pending()
    except UnknownFieldError as exc:
        raise ApiError(422, "UNKNOWN_FIELD", str(exc))


@router.post("/{result_id}/approve", response_model=ResultDetail)
def approve_result(result_id: str, user: CurrentUser = Depends(get_current_user)):
    try:
        return review_service.approve_result(result_id, user)
    except ResultNotFoundError:
        raise _not_found()
    except ReviewNotPendingError:
        raise _not_pending()
    except MissingRequiredFieldsError as exc:
        raise ApiError(422, "REQUIRED_FIELDS_MISSING", str(exc))