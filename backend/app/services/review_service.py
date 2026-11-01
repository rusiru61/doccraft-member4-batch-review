from datetime import datetime, timezone

from app.core.config import settings
from app.integrations.auth_service import CurrentUser
from app.repositories import batch_repository
from app.repositories import review_repository as repo
from app.schemas.audit import AuditAction
from app.schemas.data_structure import FieldDefinition
from app.schemas.extraction import ExtractionResult
from app.schemas.review import (
    CorrectionRequest, ReviewFieldView, ReviewStatus, ReviewTaskDetail, ReviewTaskResponse,
)
from app.services import audit_service, extraction_rules


class TaskNotFoundError(Exception):
    pass


class TaskNotPendingError(Exception):
    pass


class UnknownFieldError(Exception):
    def __init__(self, names: list[str]):
        super().__init__(f"Unknown field IDs: {names}")


class MissingRequiredFieldsError(Exception):
    def __init__(self, names: list[str]):
        super().__init__(f"Required fields still unresolved: {names}")


def needs_review(score: float) -> bool:
    """A score exactly equal to the threshold passes (US-06 AC2)."""
    return score < settings.reliability_threshold


def _definitions(item: dict) -> list[FieldDefinition]:
    return [FieldDefinition(**d) for d in item["field_definitions"]]


def flag_if_needed(
    item: dict,
    result: ExtractionResult,
    definitions: list[FieldDefinition],
    score: float,
    force_review: bool = False,
) -> bool:
    field_values = result.model_dump()["field_values"]
    reasons = []
    if needs_review(score):
        reasons.append("low_reliability")
    if extraction_rules.find_required_problems(field_values, definitions):
        reasons.append("required_field_problem")
    if force_review:
        reasons.append("unknown_language")
    if not reasons:
        return False

    repo.upsert_task(
        {
            "task_id": f"REV-{item['item_id']}",
            "batch_id": item["batch_id"],
            "item_id": item["item_id"],
            "document_id": item["document_id"],
            "filename": item["filename"],
            "reliability_score": score,
            "flagged_fields": extraction_rules.find_flagged_fields(field_values),
            "review_reasons": reasons,
            "status": ReviewStatus.pending.value,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return True


def list_queue(status: ReviewStatus | None) -> list[ReviewTaskResponse]:
    value = status.value if status else None
    return [ReviewTaskResponse(**t) for t in repo.list_tasks(value)]


def get_task_detail(task_id: str) -> ReviewTaskDetail:
    task = repo.find_task(task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    item = batch_repository.find_item(task["item_id"])
    field_values = item["extraction"]["field_values"]
    corrections = task.get("corrections", {})

    fields = []
    for d in sorted(_definitions(item), key=lambda d: d.order):
        original = field_values.get(d.field_id) or {"value": None, "status": "missing", "source_text": None}
        corrected = d.field_id in corrections
        fields.append(
            ReviewFieldView(
                field_id=d.field_id,
                name=d.name,
                type=d.type,
                required=d.required,
                original_value=original["value"],
                current_value=corrections[d.field_id]["value"] if corrected else original["value"],
                status="corrected" if corrected else original["status"],
                source_text=original["source_text"],
                flagged=d.field_id in task["flagged_fields"],
            )
        )
    return ReviewTaskDetail(
        **task, fields=fields, validation_errors=item["extraction"]["validation_errors"]
    )


def apply_corrections(
    task_id: str, request: CorrectionRequest, user: CurrentUser
) -> ReviewTaskDetail:
    task = repo.find_task(task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    if task["status"] != ReviewStatus.pending.value:
        raise TaskNotPendingError(task_id)

    item = batch_repository.find_item(task["item_id"])
    known = {d.field_id for d in _definitions(item)}
    unknown = [c.field_id for c in request.corrections if c.field_id not in known]
    if unknown:
        raise UnknownFieldError(unknown)

    field_values = item["extraction"]["field_values"]
    previous = task.get("corrections", {})
    changes = {
        c.field_id: {
            "from": previous[c.field_id]["value"]
            if c.field_id in previous
            else (field_values.get(c.field_id) or {}).get("value"),
            "to": c.value,
        }
        for c in request.corrections
    }

    now = datetime.now(timezone.utc)
    merged = dict(previous)
    for c in request.corrections:
        merged[c.field_id] = {"value": c.value, "corrected_by": user.user_id, "corrected_at": now}

    if not repo.save_corrections(task_id, merged):
        raise TaskNotPendingError(task_id)  # the task was completed in the meantime
    audit_service.record(
        user.user_id,
        AuditAction.fields_corrected,
        "review_task",
        task_id,
        task["batch_id"],
        {"document_id": task["document_id"], "changes": changes},
    )
    return get_task_detail(task_id)


def auto_finalize(item: dict, result: ExtractionResult, definitions: list[FieldDefinition]) -> None:
    """High-scoring documents with no problems need no review, so the system finalizes them."""
    batch_repository.update_item(
        item["item_id"],
        {
            "review_status": "not_required",
            "final_fields": extraction_rules.build_final_fields(
                result.model_dump()["field_values"], {}, definitions
            ),
            "finalized_by": "system",
            "finalized_at": datetime.now(timezone.utc),
        },
    )


def finalize_task(task_id: str, user: CurrentUser) -> ReviewTaskDetail:
    task = repo.find_task(task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    if task["status"] != ReviewStatus.pending.value:
        raise TaskNotPendingError(task_id)

    item = batch_repository.find_item(task["item_id"])
    definitions = _definitions(item)
    final_fields = extraction_rules.build_final_fields(
        item["extraction"]["field_values"], task.get("corrections", {}), definitions
    )
    required = {d.field_id for d in definitions if d.required}
    unresolved = [
        f["field_id"]
        for f in final_fields
        if f["field_id"] in required and f["status"] in extraction_rules.PROBLEM_STATUSES
    ]
    if unresolved:
        raise MissingRequiredFieldsError(unresolved)

    now = datetime.now(timezone.utc)
    if not repo.approve_task(task_id, user.user_id, now):
        raise TaskNotPendingError(task_id)  # someone else approved it first

    batch_repository.update_item(
        item["item_id"],
        {
            "review_status": "approved",
            "final_fields": final_fields,
            "finalized_by": user.user_id,
            "finalized_at": now,
        },
    )
    audit_service.record(
        user.user_id,
        AuditAction.task_approved,
        "review_task",
        task_id,
        task["batch_id"],
        {
            "document_id": task["document_id"],
            "corrected_fields": [f["field_id"] for f in final_fields if f["status"] == "corrected"],
        },
    )
    return get_task_detail(task_id)