from fastapi import APIRouter, Query

from app.schemas.audit import AuditAction, AuditLogPage
from app.services import audit_service

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get("", response_model=AuditLogPage)
def list_audit_log(
    user_id: str | None = None,
    action: AuditAction | None = None,
    job_id: str | None = None,
    entity_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Read-only record of who did what, newest first."""
    return audit_service.get_log(user_id, action, job_id, entity_id, page, page_size)