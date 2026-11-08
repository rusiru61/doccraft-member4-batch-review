from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class AuditAction(str, Enum):
    job_created = "job.created"
    processing_started = "job.processing_started"
    job_finalized = "job.finalized"
    fields_corrected = "review.fields_corrected"
    result_approved = "review.result_approved"


class AuditEntry(BaseModel):
    audit_id: str
    timestamp: datetime
    actor_user_id: str
    action: AuditAction
    resource_type: str
    resource_id: str
    job_id: str | None
    changed_fields: list[str]
    safe_metadata: dict


class AuditLogPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AuditEntry]