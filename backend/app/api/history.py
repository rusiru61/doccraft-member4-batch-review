from fastapi import APIRouter, Query

from app.schemas.batch import BatchStatus
from app.schemas.history import JobHistoryPage
from app.services import history_service

router = APIRouter(prefix="/job-history", tags=["history"])


@router.get("", response_model=JobHistoryPage)
def list_job_history(
    status: BatchStatus | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Past and current batch jobs, newest first."""
    return history_service.get_history(status, limit, offset)