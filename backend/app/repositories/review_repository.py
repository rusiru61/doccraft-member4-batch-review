from app.core.database import get_db


def upsert_task(task: dict) -> None:
    """Insert only if no task with this task_id exists (safe to call twice)."""
    get_db().review_tasks.update_one(
        {"task_id": task["task_id"]}, {"$setOnInsert": task}, upsert=True
    )


def list_tasks(status: str | None) -> list[dict]:
    query = {"status": status} if status else {}
    return list(
        get_db()
        .review_tasks.find(query, {"_id": 0})
        .sort([("reliability_score", 1), ("created_at", 1)])
    )

def find_task(task_id: str) -> dict | None:
    return get_db().review_tasks.find_one({"task_id": task_id}, {"_id": 0})


def save_corrections(task_id: str, corrections: dict) -> bool:
    """Only succeeds while the task is still pending."""
    result = get_db().review_tasks.update_one(
        {"task_id": task_id, "status": "pending"},
        {"$set": {"corrections": corrections}},
    )
    return result.matched_count == 1


def approve_task(task_id: str, user_id: str, when) -> bool:
    """Compare-and-set: only a still-pending task can be approved."""
    result = get_db().review_tasks.update_one(
        {"task_id": task_id, "status": "pending"},
        {"$set": {"status": "approved", "approved_by": user_id, "approved_at": when}},
    )
    return result.modified_count == 1