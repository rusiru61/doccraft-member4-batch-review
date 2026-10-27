from datetime import datetime, timezone
from uuid import uuid4

from app.repositories import audit_repository as repo
from app.schemas.audit import AuditAction, AuditEntry, AuditLogPage


def record(
    user_id: str,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    batch_id: str | None = None,
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
            "batch_id": batch_id,
            "details": details or {},
        }
    )


def get_log(
    user_id: str | None,
    action: AuditAction | None,
    batch_id: str | None,
    entity_id: str | None,
    limit: int,
    offset: int,
) -> AuditLogPage:
    filters = {
        "user_id": user_id,
        "action": action.value if action else None,
        "batch_id": batch_id,
        "entity_id": entity_id,
    }
    rows, total = repo.list_entries(filters, limit, offset)
    return AuditLogPage(
        total=total, limit=limit, offset=offset, items=[AuditEntry(**r) for r in rows]
    )