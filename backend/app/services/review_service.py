from datetime import datetime, timezone

from app.core.config import settings
from app.repositories import review_repository as repo
from app.schemas.extraction import ExtractionResult
from app.schemas.review import ReviewStatus, ReviewTaskResponse
from app.integrations.auth_service import CurrentUser
from app.repositories import batch_repository
from app.schemas.review import CorrectionRequest, ReviewFieldView, ReviewTaskDetail

def needs_review(score: float) -> bool:
    """A score exactly equal to the threshold passes (US-06 AC2)."""
    return score < settings.reliability_threshold


def find_flagged_fields(result: ExtractionResult) -> list[str]:
    threshold = settings.reliability_threshold
    return [f.name for f in result.fields if not f.found or f.confidence < threshold]


def flag_if_needed(item: dict, result: ExtractionResult, score: float) -> bool:
    if not needs_review(score):
        return False
    repo.upsert_task(
        {
            "task_id": f"REV-{item['item_id']}",
            "batch_id": item["batch_id"],
            "item_id": item["item_id"],
            "document_id": item["document_id"],
            "filename": item["filename"],
            "reliability_score": score,
            "flagged_fields": find_flagged_fields(result),
            "status": ReviewStatus.pending.value,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return True


def list_queue(status: ReviewStatus | None) -> list[ReviewTaskResponse]:
    value = status.value if status else None
    return [ReviewTaskResponse(**t) for t in repo.list_tasks(value)]

class TaskNotFoundError(Exception):
    pass


class TaskNotPendingError(Exception):
    pass


class UnknownFieldError(Exception):
    def __init__(self, names: list[str]):
        super().__init__(f"Unknown field names: {names}")


def get_task_detail(task_id: str) -> ReviewTaskDetail:
    task = repo.find_task(task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    item = batch_repository.find_item(task["item_id"])
    extraction = item["extraction"]
    corrections = task.get("corrections", {})

    fields = []
    for f in extraction["fields"]:
        corrected = f["name"] in corrections
        fields.append(
            ReviewFieldView(
                name=f["name"],
                original_value=f["value"],
                current_value=corrections[f["name"]]["value"] if corrected else f["value"],
                confidence=f["confidence"],
                found=f["found"],
                required=f["required"],
                flagged=f["name"] in task["flagged_fields"],
                corrected=corrected,
            )
        )
    return ReviewTaskDetail(
        **task, fields=fields, validation_errors=extraction["validation_errors"]
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
    known = {f["name"] for f in item["extraction"]["fields"]}
    unknown = [c.name for c in request.corrections if c.name not in known]
    if unknown:
        raise UnknownFieldError(unknown)

    now = datetime.now(timezone.utc)
    merged = dict(task.get("corrections", {}))
    for c in request.corrections:
        merged[c.name] = {"value": c.value, "corrected_by": user.user_id, "corrected_at": now}

    if not repo.save_corrections(task_id, merged):
        raise TaskNotPendingError(task_id)  # the task was completed in the meantime
    return get_task_detail(task_id)