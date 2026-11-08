from fastapi import APIRouter, Depends

from app.integrations.auth_service import CurrentUser, require_roles
from app.schemas.results import FinalizedResult
from app.services import permissions, results_service

router = APIRouter(prefix="/finalized-results", tags=["finalized-results"])


@router.get("", response_model=list[FinalizedResult])
def list_finalized_results(
    job_id: str | None = None,
    user: CurrentUser = Depends(require_roles(*permissions.VIEW_RESULTS)),
):
    """Gate G5: your results that are ready to hand to Member 5's export module."""
    return results_service.list_finalized(job_id, permissions.owner_scope(user))