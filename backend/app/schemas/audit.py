from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class AuditAction(str, Enum):
    batch_created = "batch.created"
    processing_started = "batch.processing_started"
    fields_corrected = "review.fields_corrected"
    task_approved = "review.task_approved"


class AuditEntry(BaseModel):
    audit_id: str
    timestamp: datetime
    user_id: str
    action: AuditAction
    entity_type: str
    entity_id: str
    batch_id: str | None
    details: dict


class AuditLogPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AuditEntry]