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
    db.extraction_jobs.create_index([("created_at", DESCENDING), ("_id", ASCENDING)])

    # One result per document per job, enforced by the database itself.
    db.extraction_results.create_index(
        [("job_id", ASCENDING), ("document_id", ASCENDING)], unique=True
    )
    # The review queue: filter by review status, already sorted by score.
    db.extraction_results.create_index(
        [("review_status", ASCENDING), ("reliability_score", ASCENDING), ("created_at", ASCENDING)]
    )
    # The finalized-results handoff.
    db.extraction_results.create_index([("review_status", ASCENDING), ("finalized_at", ASCENDING)])

    db.audit_logs.create_index("audit_id", unique=True)
    db.audit_logs.create_index([("timestamp", DESCENDING)])
    db.audit_logs.create_index("job_id")