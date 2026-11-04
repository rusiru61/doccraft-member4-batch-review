import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
ALLOWED_ERROR_KEYS = {"code", "message", "details", "request_id"}


def _create(ids=("DOC-001",)):
    body = {"name": "T", "priority": "high", "document_ids": list(ids)}
    return client.post("/api/v1/jobs", json=body).json()["job_id"]


def test_api_is_served_under_the_v1_prefix():
    assert client.get("/api/v1/jobs").status_code == 200


def test_old_unprefixed_paths_are_gone():
    for path in ("/jobs", "/review-tasks", "/job-history", "/audit-log"):
        assert client.get(path).status_code == 404


def test_health_stays_at_the_root():
    assert client.get("/health").json() == {"status": "ok"}


def test_not_found_uses_the_contract_error_format():
    response = client.get("/api/v1/jobs/JOB-NOPE")
    body = response.json()
    assert response.status_code == 404
    assert "detail" not in body
    assert body["error"]["code"] == "JOB_NOT_FOUND"
    assert body["error"]["message"]


def test_validation_error_has_field_details_and_never_echoes_input():
    response = client.post(
        "/api/v1/jobs", json={"name": "T", "priority": "high", "document_ids": []}
    )
    error = response.json()["error"]
    assert response.status_code == 422
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "body.document_ids"
    assert set(error["details"][0]) == {"field", "message"}


def test_conflict_has_a_stable_code():
    job_id = _create()
    client.post(f"/api/v1/jobs/{job_id}/process")
    response = client.post(f"/api/v1/jobs/{job_id}/process")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_ALREADY_STARTED"


def test_unknown_route_and_wrong_method_use_the_contract_format():
    missing = client.get("/api/v1/nothing")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"

    wrong_method = client.delete("/api/v1/audit-log")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_every_error_body_contains_only_documented_keys():
    responses = [
        client.get("/api/v1/jobs/JOB-NOPE"),
        client.post("/api/v1/jobs/JOB-NOPE/process"),
        client.post("/api/v1/jobs", json={}),
        client.delete("/api/v1/audit-log"),
    ]
    for response in responses:
        body = response.json()
        assert set(body) == {"error"}
        assert set(body["error"]) <= ALLOWED_ERROR_KEYS


def test_paginated_lists_use_page_and_page_size():
    for path in ("/api/v1/job-history", "/api/v1/audit-log"):
        body = client.get(path).json()
        assert {"items", "total", "page", "page_size"} <= set(body)
        assert "limit" not in body and "offset" not in body
        assert (body["page"], body["page_size"]) == (1, 20)