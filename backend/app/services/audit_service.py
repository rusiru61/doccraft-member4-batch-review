from datetime import datetime, timezone

from app.repositories import audit_repository as repo
from app.schemas.audit import AuditAction, AuditEntry, AuditLogPage


def record(
    actor_user_id: str,
    action: AuditAction,
    resource_type: str,
    resource_id: str,
    job_id: str | None = None,
    changed_fields: list[str] | None = None,
    safe_metadata: dict | None = None,
) -> None:
    """Append one audit entry. Field IDs only: never document contents, secrets or headers."""
    repo.insert_entry(
        {
            "timestamp": datetime.now(timezone.utc),
            "actor_user_id": actor_user_id,
            "action": action.value,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "job_id": job_id,
            "changed_fields": changed_fields or [],
            "safe_metadata": safe_metadata or {},
        }
    )


def _to_entry(doc: dict) -> AuditEntry:
    doc = dict(doc)
    doc["audit_id"] = str(doc.pop("_id"))
    return AuditEntry(**doc)


def get_log(
    actor_user_id: str | None,
    action: AuditAction | None,
    resource_type: str | None,
    resource_id: str | None,
    job_id: str | None,
    page: int,
    page_size: int,
) -> AuditLogPage:
    filters = {
        "actor_user_id": actor_user_id,
        "action": action.value if action else None,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "job_id": job_id,
    }
    rows, total = repo.list_entries(filters, page_size, (page - 1) * page_size)
    return AuditLogPage(
        total=total, page=page, page_size=page_size, items=[_to_entry(r) for r in rows]
    )