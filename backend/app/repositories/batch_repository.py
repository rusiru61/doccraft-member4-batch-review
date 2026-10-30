from app.core.database import get_db
from datetime import datetime, timezone


def insert_batch(batch: dict, items: list[dict]) -> None:
    db = get_db()
    # Items first: if this fails, no batch exists. A batch with no items would look broken.
    db.job_items.insert_many([dict(i) for i in items])
    db.batches.insert_one(dict(batch))  # dict() copy: pymongo adds _id to what it receives


def find_batch(batch_id: str) -> dict | None:
    return get_db().batches.find_one({"batch_id": batch_id}, {"_id": 0})


def list_batches() -> list[dict]:
    return list(get_db().batches.find({}, {"_id": 0}).sort("created_at", -1))


def list_items(batch_id: str) -> list[dict]:
    return list(get_db().job_items.find({"batch_id": batch_id}, {"_id": 0}))


def count_by_status(batch_id: str) -> dict[str, int]:
    pipeline = [
        {"$match": {"batch_id": batch_id}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    return {row["_id"]: row["count"] for row in get_db().job_items.aggregate(pipeline)}

def try_mark_batch_processing(batch_id: str) -> bool:
    """Compare-and-set: succeeds only if the batch is still 'pending'."""
    result = get_db().batches.update_one(
        {"batch_id": batch_id, "status": "pending"},
        {"$set": {"status": "processing", "started_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count == 1


def set_batch_status(batch_id: str, status: str) -> None:
    fields = {"status": status}
    if status == "completed":
        fields["completed_at"] = datetime.now(timezone.utc)
    get_db().batches.update_one({"batch_id": batch_id}, {"$set": fields})


def list_batches_page(status: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    query = {"status": status} if status else {}
    collection = get_db().batches
    rows = list(
        collection.find(query, {"_id": 0})
        .sort([("created_at", -1), ("batch_id", 1)])
        .skip(offset)
        .limit(limit)
    )
    return rows, collection.count_documents(query)


def summarize_items(batch_ids: list[str]) -> dict[str, dict]:
    """One database round trip for all batches (avoids one query per batch)."""
    pipeline = [
        {"$match": {"batch_id": {"$in": batch_ids}}},
        {
            "$group": {
                "_id": "$batch_id",
                "total": {"$sum": 1},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
                "processing": {"$sum": {"$cond": [{"$eq": ["$status", "processing"]}, 1, 0]}},
                "pending_review": {
                    "$sum": {"$cond": [{"$eq": ["$review_status", "pending_review"]}, 1, 0]}
                },
            }
        },
    ]
    return {row["_id"]: row for row in get_db().job_items.aggregate(pipeline)}


def update_item(item_id: str, fields: dict) -> None:
    get_db().job_items.update_one({"item_id": item_id}, {"$set": fields})

def find_item(item_id: str) -> dict | None:
    return get_db().job_items.find_one({"item_id": item_id}, {"_id": 0})

def list_finalized(batch_id: str | None) -> list[dict]:
    query: dict = {"review_status": {"$in": ["not_required", "approved"]}}
    if batch_id:
        query["batch_id"] = batch_id
    return list(
        get_db().job_items.find(query, {"_id": 0}).sort([("finalized_at", 1), ("document_id", 1)])
    )

def revert_batch_to_pending(batch_id: str) -> None:
    """Undo the 'processing' mark when the job could not be queued."""
    get_db().batches.update_one(
        {"batch_id": batch_id, "status": "processing"},
        {"$set": {"status": "pending", "started_at": None}},
    )