import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.core.logging_config import RequestIdFilter, request_id_var
from app.core.middleware import request_context_middleware
from app.main import app

client = TestClient(app)


def _app_that_crashes() -> FastAPI:
    test_app = FastAPI()
    test_app.middleware("http")(request_context_middleware)

    @test_app.get("/boom")
    def boom():
        raise RuntimeError("secret internal detail: password is hunter2")

    return test_app


def test_every_response_has_a_request_id_header():
    response = client.get("/health")
    assert len(response.headers["X-Request-ID"]) == 12


def test_each_request_gets_its_own_id():
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert first != second


def test_requests_are_logged_with_method_path_and_status(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/health")
    assert any("GET /health -> 200" in r.getMessage() for r in caplog.records)


def test_log_records_carry_the_request_id():
    token = request_id_var.set("abc123")
    try:
        record = logging.LogRecord("x", logging.INFO, "f", 1, "msg", None, None)
        RequestIdFilter().filter(record)
        assert record.request_id == "abc123"
    finally:
        request_id_var.reset(token)


def test_unexpected_error_returns_clean_500_without_internals():
    response = TestClient(_app_that_crashes()).get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert "hunter2" not in response.text
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_unexpected_error_is_logged_with_a_stack_trace(caplog):
    with caplog.at_level(logging.ERROR):
        TestClient(_app_that_crashes()).get("/boom")
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors and errors[0].exc_info is not None


def test_database_outage_returns_503_with_request_id(monkeypatch):
    def database_down():
        raise ServerSelectionTimeoutError("mongo is down")

    monkeypatch.setattr("app.repositories.batch_repository.list_batches", database_down)
    response = client.get("/batches")
    assert response.status_code == 503
    body = response.json()
    assert body["detail"] == "Database unavailable"
    assert body["request_id"] == response.headers["X-Request-ID"]