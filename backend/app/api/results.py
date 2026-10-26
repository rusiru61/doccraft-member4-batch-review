from fastapi import APIRouter

from app.schemas.results import FinalizedResult
from app.services import results_service

router = APIRouter(prefix="/finalized-results", tags=["results"])


@router.get("", response_model=list[FinalizedResult])
def list_finalized_results(batch_id: str | None = None):
    """Gate G5: everything that is ready to hand to Member 5's export module."""
    return results_service.list_finalized(batch_id)