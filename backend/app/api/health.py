from fastapi import APIRouter, HTTPException
from pymongo.errors import PyMongoError

from app.core.database import get_client

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
        raise HTTPException(status_code=503, detail="Database unavailable")