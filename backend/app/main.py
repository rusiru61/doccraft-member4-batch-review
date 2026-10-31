import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api import audit, batches, health, history, results, review
from app.core.config import settings
from app.core.database import ensure_indexes
from app.core.logging_config import request_id_var, setup_logging
from app.core.middleware import request_context_middleware

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


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


@app.exception_handler(PyMongoError)
async def database_error_handler(request: Request, exc: PyMongoError):
    """A database outage is an expected failure, so answer 503 rather than a generic 500."""
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable", "request_id": request_id_var.get()},
    )


app.include_router(health.router)
app.include_router(batches.router)
app.include_router(review.router)
app.include_router(results.router)
app.include_router(history.router)
app.include_router(audit.router)