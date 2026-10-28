from fastapi import FastAPI

from app.api import batches, health, review, results, history, audit
from app.core.config import settings

import logging
from contextlib import asynccontextmanager

from pymongo.errors import PyMongoError

from app.core.database import ensure_indexes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_indexes()
    except PyMongoError:
        # Don't crash: /health/db exists to report this problem clearly.
        logger.exception("Could not create database indexes at startup")
    yield


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health.router)
app.include_router(batches.router)
app.include_router(review.router)
app.include_router(results.router)
app.include_router(history.router)
app.include_router(audit.router)