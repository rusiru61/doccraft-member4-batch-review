import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from pymongo.errors import PyMongoError

from app.api import audit, batches, health, history, results, review
from app.core.config import settings
from app.core.database import ensure_indexes
from app.core.errors import register_error_handlers
from app.core.logging_config import setup_logging
from app.core.middleware import request_context_middleware

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        ensure_indexes()
    except PyMongoError:
        # Don't crash: /health/db exists to report this problem clearly.
        logger.exception("Could not create database indexes at startup")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.middleware("http")(request_context_middleware)
register_error_handlers(app)

# Health checks stay at the root, as the team contract specifies.
app.include_router(health.router)

# Everything else lives under the versioned prefix.
api_v1 = APIRouter(prefix=API_PREFIX)
api_v1.include_router(batches.router)
api_v1.include_router(review.router)
api_v1.include_router(results.router)
api_v1.include_router(history.router)
api_v1.include_router(audit.router)
app.include_router(api_v1)