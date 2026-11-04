from datetime import datetime, timezone

from bson import ObjectId

from app.core.database import get_db
from app.core.ids import to_object_id


def job_from_doc(doc: dict | None) -> dict | None:
    """Database document -> the dict the services use (batch_id is the string form of _id)."""
    if doc is None:
        return None
    doc = dict(doc)
    doc["batch_id"] = str(doc.pop("_id"))
    return doc


def result_from_doc(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc = dict(doc)
    doc["item_id"] = str(doc.pop("_id"))
    doc["batch_id"] = str(doc.pop("job_id"))
    return doc


def insert_batch(batch: dict, items: list[dict]) -> str:
    """Store a job and its results. Returns the new job ID as a string."""
    db = get_db()
    job_id = ObjectId()
    # Results first: if this fails, no job exists. A job with no results would look broken.
    db.extraction_results.insert_many([{**item, "job_id": job_id} for item in items])
    db.extraction_jobs.insert_one({**batch, "_id": job_id})
    return str(job_id)


def find_batch(batch_id: str) -> dict | None:
    oid = to_object_id(batch_id)
    if oid is None:
        return None
    return job_from_doc(get_db().extraction_jobs.find_one({"_id": oid}))


def list_batches() -> list[dict]:
    rows = get_db().extraction_jobs.find({}).sort([("created_at", -1), ("_id", 1)])
    return [job_from_doc(d) for d in rows]


def list_items(batch_id: str) -> list[dict]:
    oid = to_object_id(batch_id)
    if oid is None:
        return []
    rows = get_db().extraction_results.find({"job_id": oid}).sort("_id", 1)
    return [result_from_doc(d) for d in rows]


def find_item(item_id: str) -> dict | None:
    oid = to_object_id(item_id)
    if oid is None:
        return None
    return result_from_doc(get_db().extraction_results.find_one({"_id": oid}))


def count_by_status(batch_id: str) -> dict[str, int]:
    oid = to_object_id(batch_id)
    if oid is None:
        return {}
    pipeline = [
        {"$match": {"job_id": oid}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    return {row["_id"]: row["count"] for row in get_db().extraction_results.aggregate(pipeline)}


def try_mark_batch_processing(batch_id: str) -> bool:
    """Compare-and-set: succeeds only if the batch is still 'pending'."""
    oid = to_object_id(batch_id)
    if oid is None:
        return False
    result = get_db().extraction_jobs.update_one(
        {"_id": oid, "status": "pending"}, {"$set": {"status": "processing"}}
    )
    return result.modified_count == 1


def mark_batch_started(batch_id: str) -> None:
    """Called by the worker. Keeps the first start time if the batch is resumed."""
    oid = to_object_id(batch_id)
    if oid is None:
        return
    get_db().extraction_jobs.update_one(
        {"_id": oid, "started_at": None},
        {"$set": {"started_at": datetime.now(timezone.utc)}},
    )


def set_batch_status(batch_id: str, status: str) -> None:
    oid = to_object_id(batch_id)
    if oid is None:
        return
    fields = {"status": status}
    if status == "completed":
        fields["completed_at"] = datetime.now(timezone.utc)
    get_db().extraction_jobs.update_one({"_id": oid}, {"$set": fields})


def revert_batch_to_pending(batch_id: str) -> None:
    """Undo the 'processing' mark when the job could not be queued."""
    oid = to_object_id(batch_id)
    if oid is None:
        return
    get_db().extraction_jobs.update_one(
        {"_id": oid, "status": "processing"}, {"$set": {"status": "pending", "started_at": None}}
    )


def update_item(item_id: str, fields: dict) -> None:
    oid = to_object_id(item_id)
    if oid is None:
        return
    get_db().extraction_results.update_one({"_id": oid}, {"$set": fields})


def list_finalized(batch_id: str | None) -> list[dict]:
    query: dict = {"review_status": {"$in": ["not_required", "approved"]}}
    if batch_id:
        oid = to_object_id(batch_id)
        if oid is None:
            return []
        query["job_id"] = oid
    rows = get_db().extraction_results.find(query).sort([("finalized_at", 1), ("document_id", 1)])
    return [result_from_doc(d) for d in rows]


def list_batches_page(status: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    query = {"status": status} if status else {}
    collection = get_db().extraction_jobs
    rows = (
        collection.find(query)
        .sort([("created_at", -1), ("_id", 1)])
        .skip(offset)
        .limit(limit)
    )
    return [job_from_doc(d) for d in rows], collection.count_documents(query)


def summarize_items(batch_ids: list[str]) -> dict[str, dict]:
    """One database round trip for all jobs (avoids one query per job)."""
    oids = [oid for oid in map(to_object_id, batch_ids) if oid is not None]
    pipeline = [
        {"$match": {"job_id": {"$in": oids}}},
        {
            "$group": {
                "_id": "$job_id",
                "total": {"$sum": 1},
                "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}},
                "processing": {"$sum": {"$cond": [{"$eq": ["$status", "processing"]}, 1, 0]}},
                "completed": {"$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
                "pending_review": {
                    "$sum": {"$cond": [{"$eq": ["$review_status", "pending_review"]}, 1, 0]}
                },
            }
        },
    ]
    return {str(row["_id"]): row for row in get_db().extraction_results.aggregate(pipeline)}