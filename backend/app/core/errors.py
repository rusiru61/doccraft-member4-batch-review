import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging_config import request_id_var

logger = logging.getLogger(__name__)

# Fallback codes for errors we didn't raise ourselves (unknown route, wrong method...).
_CODE_BY_STATUS = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_FILE_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(Exception):
    """An expected failure, with a stable machine-readable code."""

    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(
    status_code: int, code: str, message: str, details: list[dict] | None = None
) -> JSONResponse:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    request_id = request_id_var.get()
    if request_id != "-":
        error["request_id"] = request_id
    return JSONResponse(status_code=status_code, content={"error": error})


async def api_error_handler(request: Request, exc: ApiError):
    return error_response(exc.status_code, exc.code, exc.message)


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = _CODE_BY_STATUS.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Only the location and message: never echo what the client sent.
    details = [
        {"field": ".".join(str(part) for part in e["loc"]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return error_response(
        422, "VALIDATION_ERROR", "The request contains invalid data.", details
    )


async def database_error_handler(request: Request, exc: PyMongoError):
    """A database outage is an expected failure, so answer 503 rather than a generic 500."""
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(503, "DATABASE_UNAVAILABLE", "Database unavailable")


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(PyMongoError, database_error_handler)