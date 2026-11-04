from bson import ObjectId
from bson.errors import InvalidId


def to_object_id(value) -> ObjectId | None:
    """Turn a client-supplied ID into an ObjectId, or None if it is not a valid one."""
    if not isinstance(value, str) or len(value) != 24:
        return None
    try:
        return ObjectId(value)
    except InvalidId:
        return None