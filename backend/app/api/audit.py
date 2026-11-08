from fastapi import APIRouter, Depends, Query

from app.integrations.auth_service import require_roles
from app.schemas.audit import AuditAction, AuditLogPage
from app.services import audit_service, permissions

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get(
    "",
    response_model=AuditLogPage,
    dependencies=[Depends(require_roles(*permissions.VIEW_AUDIT_LOG))],
)
def list_audit_logs(
    actor_user_id: str | None = None,
    action: AuditAction | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    job_id: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Admin only. Read-only record of who did what, newest first."""
    return audit_service.get_log(
        actor_user_id, action, resource_type, resource_id, job_id, page, page_size
    )