from fastapi import APIRouter, Query

from app.schemas.audit import AuditAction, AuditLogPage
from app.services import audit_service

router = APIRouter(prefix="/audit-log", tags=["audit"])


@router.get("", response_model=AuditLogPage)
def list_audit_log(
    user_id: str | None = None,
    action: AuditAction | None = None,
    batch_id: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Read-only record of who did what, newest first."""
    return audit_service.get_log(user_id, action, batch_id, entity_id, limit, offset)