from datetime import datetime, timezone

from app.core.config import settings
from app.integrations.auth_service import CurrentUser
from app.repositories import job_repository
from app.repositories import review_repository as repo
from app.schemas.audit import AuditAction
from app.schemas.data_structure import FieldDefinition
from app.schemas.extraction import ExtractionResult
from app.schemas.review import (
    CorrectionRequest, ResultDetail, ResultSummary, ReviewFieldView, ReviewStatus,
)
from app.services import audit_service, extraction_rules, permissions


class ResultNotFoundError(Exception):
    pass


class ReviewNotPendingError(Exception):
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


def decide_review(
    result: ExtractionResult,
    definitions: list[FieldDefinition],
    score: float,
    force_review: bool = False,
) -> dict:
    """What to store on a result right after extraction. Pure: no database access.

    The decision is saved in the same write as the extraction, so a result can
    never exist without one.
    """
    field_values = result.model_dump()["field_values"]
    reasons = []
    if needs_review(score):
        reasons.append("low_reliability")
    if extraction_rules.find_required_problems(field_values, definitions):
        reasons.append("required_field_problem")
    if force_review:
        reasons.append("unknown_language")

    decision = {
        "review_reasons": reasons,
        "flagged_fields": extraction_rules.find_flagged_fields(field_values),
    }
    if reasons:
        return {**decision, "review_status": "pending_review"}
    return {
        **decision,
        "review_status": "not_required",
        "final_fields": extraction_rules.build_final_fields(field_values, {}, definitions),
        "finalized_by": "system",
        "finalized_at": datetime.now(timezone.utc),
    }


def _definitions(result: dict) -> list[FieldDefinition]:
    return [FieldDefinition(**d) for d in result["field_definitions"]]


def _load_result(result_id: str, user: CurrentUser) -> dict:
    """Failed, unknown and other people's results are all 'not found'."""
    result = job_repository.find_item(result_id)
    if (
        result is None
        or result.get("status") != "completed"
        or not permissions.can_access(user, result.get("created_by"))
    ):
        raise ResultNotFoundError(result_id)
    return result


def list_results(
    review_status: ReviewStatus, job_id: str | None, user: CurrentUser
) -> list[ResultSummary]:
    rows = repo.list_results(review_status.value, job_id, permissions.owner_scope(user))
    return [ResultSummary(**r) for r in rows]


def get_result_detail(result_id: str, user: CurrentUser) -> ResultDetail:
    result = _load_result(result_id, user)
    field_values = result["field_values"]
    corrections = result.get("corrections", {})

    fields = []
    for d in sorted(_definitions(result), key=lambda d: d.order):
        original = field_values.get(d.field_id) or {
            "value": None, "status": "missing", "source_text": None,
        }
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
                flagged=d.field_id in result["flagged_fields"],
            )
        )

    return ResultDetail(
        **{**result, "fields": fields, "validation_errors": result["validation_errors"]}
    )


def apply_corrections(
    result_id: str, request: CorrectionRequest, user: CurrentUser
) -> ResultDetail:
    result = _load_result(result_id, user)
    if result["review_status"] != "pending_review":
        raise ReviewNotPendingError(result_id)

    known = {d.field_id for d in _definitions(result)}
    unknown = [c.field_id for c in request.corrections if c.field_id not in known]
    if unknown:
        raise UnknownFieldError(unknown)

    now = datetime.now(timezone.utc)
    merged = dict(result.get("corrections", {}))
    for c in request.corrections:
        merged[c.field_id] = {"value": c.value, "corrected_by": user.user_id, "corrected_at": now}

    if not repo.save_corrections(result_id, merged):
        raise ReviewNotPendingError(result_id)  # it was approved in the meantime
    audit_service.record(
        user.user_id,
        AuditAction.fields_corrected,
        "extraction_result",
        result_id,
        result["job_id"],
        changed_fields=[c.field_id for c in request.corrections],
        safe_metadata={"document_id": result["document_id"]},
    )
    return get_result_detail(result_id, user)


def approve_result(result_id: str, user: CurrentUser) -> ResultDetail:
    result = _load_result(result_id, user)
    if result["review_status"] != "pending_review":
        raise ReviewNotPendingError(result_id)

    definitions = _definitions(result)
    final_fields = extraction_rules.build_final_fields(
        result["field_values"], result.get("corrections", {}), definitions
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
    if not repo.approve_result(result_id, user.user_id, now, final_fields):
        raise ReviewNotPendingError(result_id)  # someone else approved it first
    audit_service.record(
        user.user_id,
        AuditAction.result_approved,
        "extraction_result",
        result_id,
        result["job_id"],
        changed_fields=[f["field_id"] for f in final_fields if f["status"] == "corrected"],
        safe_metadata={"document_id": result["document_id"]},
    )
    return get_result_detail(result_id, user)