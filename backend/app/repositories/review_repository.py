from app.core.database import get_db
from app.core.ids import to_object_id
from app.repositories import job_repository


def list_results(
    review_status: str, job_id: str | None = None, created_by: str | None = None
) -> list[dict]:
    """The review queue and its siblings: results with a given review status, lowest score first."""
    query: dict = {"review_status": review_status}
    if created_by is not None:
        query["created_by"] = created_by
    if job_id is not None:
        oid = to_object_id(job_id)
        if oid is None:
            return []
        query["job_id"] = oid
    rows = (
        get_db()
        .extraction_results.find(query)
        .sort([("reliability_score", 1), ("created_at", 1), ("_id", 1)])
    )
    return [job_repository.result_from_doc(d) for d in rows]


def save_corrections(result_id: str, corrections: dict) -> bool:
    """Only succeeds while the result is still waiting for review."""
    oid = to_object_id(result_id)
    if oid is None:
        return False
    outcome = get_db().extraction_results.update_one(
        {"_id": oid, "review_status": "pending_review"},
        {"$set": {"corrections": corrections}},
    )
    return outcome.matched_count == 1


def approve_result(result_id: str, user_id: str, when, final_fields: list[dict]) -> bool:
    """Compare-and-set in ONE write: status, final values and reviewer are saved together."""
    oid = to_object_id(result_id)
    if oid is None:
        return False
    outcome = get_db().extraction_results.update_one(
        {"_id": oid, "review_status": "pending_review"},
        {
            "$set": {
                "review_status": "approved",
                "final_fields": final_fields,
                "finalized_by": user_id,
                "finalized_at": when,
                "reviewed_by": user_id,
                "reviewed_at": when,
            }
        },
    )
    return outcome.modified_count == 1