from fastapi import APIRouter, Query

from app.schemas.job import JobStatus
from app.schemas.history import JobHistoryPage
from app.services import history_service

router = APIRouter(prefix="/job-history", tags=["history"])


@router.get("", response_model=JobHistoryPage)
def list_job_history(
    status: JobStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Past and current job jobs, newest first."""
    return history_service.get_history(status, page, page_size)