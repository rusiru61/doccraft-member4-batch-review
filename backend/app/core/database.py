from pymongo import MongoClient
from pymongo.database import Database

from app.core.config import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Create the client once and reuse it (creating many is wasteful)."""
    global _client
    if _client is None:
        _client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=3000)
    return _client


def get_db() -> Database:
    return get_client()[settings.mongodb_db_name]