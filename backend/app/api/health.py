from fastapi import APIRouter
from pymongo.errors import PyMongoError

from app.core.database import get_client
from app.core.errors import ApiError

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/health/db")
def health_db():
    try:
        get_client().admin.command("ping")
        return {"database": "connected"}
    except PyMongoError:
        raise ApiError(503, "DATABASE_UNAVAILABLE", "Database unavailable")