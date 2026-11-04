from datetime import datetime, timezone
from uuid import uuid4

from app.repositories import audit_repository as repo
from app.schemas.audit import AuditAction, AuditEntry, AuditLogPage


def record(
    user_id: str,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    job_id: str | None = None,
    details: dict | None = None,
) -> None:
    repo.insert_entry(
        {
            "audit_id": f"AUD-{uuid4().hex[:12].upper()}",
            "timestamp": datetime.now(timezone.utc),
            "user_id": user_id,
            "action": action.value,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "job_id": job_id,
            "details": details or {},
        }
    )


def get_log(
    user_id: str | None,
    action: AuditAction | None,
    job_id: str | None,
    entity_id: str | None,
    page: int,
    page_size: int,
) -> AuditLogPage:
    filters = {
        "user_id": user_id,
        "action": action.value if action else None,
        "job_id": job_id,
        "entity_id": entity_id,
    }
    rows, total = repo.list_entries(filters, page_size, (page - 1) * page_size)
    return AuditLogPage(
        total=total, page=page, page_size=page_size, items=[AuditEntry(**r) for r in rows]
    )