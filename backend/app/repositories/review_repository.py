from app.core.database import get_db
from app.core.ids import to_object_id
from app.repositories import batch_repository


def list_tasks(review_statuses: list[str]) -> list[dict]:
    """Review tasks are results that are waiting for, or went through, human review."""
    rows = (
        get_db()
        .extraction_results.find({"review_status": {"$in": review_statuses}})
        .sort([("reliability_score", 1), ("created_at", 1), ("_id", 1)])
    )
    return [batch_repository.result_from_doc(d) for d in rows]


def save_corrections(task_id: str, corrections: dict) -> bool:
    """Only succeeds while the result is still waiting for review."""
    oid = to_object_id(task_id)
    if oid is None:
        return False
    result = get_db().extraction_results.update_one(
        {"_id": oid, "review_status": "pending_review"},
        {"$set": {"corrections": corrections}},
    )
    return result.matched_count == 1


def approve_task(task_id: str, user_id: str, when, final_fields: list[dict]) -> bool:
    """Compare-and-set in ONE write: status, final values and approver are saved together."""
    oid = to_object_id(task_id)
    if oid is None:
        return False
    result = get_db().extraction_results.update_one(
        {"_id": oid, "review_status": "pending_review"},
        {
            "$set": {
                "review_status": "approved",
                "final_fields": final_fields,
                "finalized_by": user_id,
                "finalized_at": when,
            }
        },
    )
    return result.modified_count == 1