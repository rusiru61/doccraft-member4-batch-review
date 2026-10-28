from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from app.core.config import settings

_client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000, tz_aware=True)


def get_client() -> MongoClient:
    """Create the client once and reuse it (creating many is wasteful)."""
    global _client
    if _client is None:
        _client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
    return _client


def get_db() -> Database:
    return get_client()[settings.mongodb_db_name]


def ensure_indexes() -> None:
    """Create every index the app relies on. Safe to run repeatedly."""
    db = get_db()
    db.batches.create_index("batch_id", unique=True)
    db.batches.create_index([("created_at", DESCENDING), ("batch_id", ASCENDING)])

    db.job_items.create_index("item_id", unique=True)
    db.job_items.create_index("batch_id")
    db.job_items.create_index([("review_status", ASCENDING), ("finalized_at", ASCENDING)])

    db.review_tasks.create_index("task_id", unique=True)
    db.review_tasks.create_index(
        [("status", ASCENDING), ("reliability_score", ASCENDING), ("created_at", ASCENDING)]
    )

    db.audit_log.create_index("audit_id", unique=True)
    db.audit_log.create_index([("timestamp", DESCENDING)])
    db.audit_log.create_index("batch_id")