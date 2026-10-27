from app.core.database import get_db


def insert_entry(entry: dict) -> None:
    get_db().audit_log.insert_one(dict(entry))  # copy: pymongo adds _id to what it receives


def list_entries(filters: dict, limit: int, offset: int) -> tuple[list[dict], int]:
    query = {k: v for k, v in filters.items() if v is not None}
    collection = get_db().audit_log
    rows = list(
        collection.find(query, {"_id": 0})
        # _id grows with insertion order, so it breaks ties between entries made in the same millisecond
        .sort([("timestamp", -1), ("_id", -1)])
        .skip(offset)
        .limit(limit)
    )
    return rows, collection.count_documents(query)