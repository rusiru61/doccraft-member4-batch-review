from app.core.database import get_db


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
        {"$set": {"status": "processing"}},
    )
    return result.modified_count == 1


def set_batch_status(batch_id: str, status: str) -> None:
    get_db().batches.update_one({"batch_id": batch_id}, {"$set": {"status": status}})


def update_item(item_id: str, fields: dict) -> None:
    get_db().job_items.update_one({"item_id": item_id}, {"$set": fields})

def find_item(item_id: str) -> dict | None:
    return get_db().job_items.find_one({"item_id": item_id}, {"_id": 0})