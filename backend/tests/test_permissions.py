import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)

BASE = {"template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE"}
FIX = {"corrections": [{"field_id": "supplier_name", "value": "ABC Traders"}]}
OPERATOR = {"X-Mock-User-Id": "user_001", "X-Mock-Role": "operator"}
OTHER_OPERATOR = {"X-Mock-User-Id": "user_002", "X-Mock-Role": "operator"}
DESIGNER = {"X-Mock-User-Id": "designer_1", "X-Mock-Role": "template_designer"}
VIEWER = {"X-Mock-User-Id": "viewer_1", "X-Mock-Role": "viewer"}
ADMIN = {"X-Mock-User-Id": "admin_1", "X-Mock-Role": "admin"}
ANONYMOUS = {"X-Mock-Role": "anonymous"}
ZERO_ID = "0" * 24


def _create(headers=OPERATOR, ids=("DOC-003",), start=True):
    body = {**BASE, "document_ids": list(ids), "start": start}
    return client.post("/api/v1/extraction-jobs", json=body, headers=headers).json()["job_id"]


def _first_result_id(headers=OPERATOR):
    return client.get("/api/v1/extraction-results", headers=headers).json()[0]["result_id"]


def _job_url(job_id):
    return f"/api/v1/extraction-jobs/{job_id}"


def _result_url(result_id):
    return f"/api/v1/extraction-results/{result_id}"


UNAUTHENTICATED_CASES = [
    ("get", "/api/v1/extraction-jobs"),
    ("get", f"/api/v1/extraction-jobs/{ZERO_ID}"),
    ("get", f"/api/v1/extraction-jobs/{ZERO_ID}/results"),
    ("post", f"/api/v1/extraction-jobs/{ZERO_ID}/process"),
    ("post", f"/api/v1/extraction-jobs/{ZERO_ID}/finalize"),
    ("get", "/api/v1/extraction-results"),
    ("get", f"/api/v1/extraction-results/{ZERO_ID}"),
    ("post", f"/api/v1/extraction-results/{ZERO_ID}/approve"),
    ("get", "/api/v1/finalized-results"),
    ("get", "/api/v1/audit-logs"),
]


@pytest.mark.parametrize("method, path", UNAUTHENTICATED_CASES)
def test_unauthenticated_requests_are_rejected(method, path):
    response = getattr(client, method)(path, headers=ANONYMOUS)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_unauthenticated_create_and_correct_are_rejected():
    body = {**BASE, "document_ids": ["DOC-001"]}
    assert client.post("/api/v1/extraction-jobs", json=body, headers=ANONYMOUS).status_code == 401
    assert client.patch(_result_url(ZERO_ID), json=FIX, headers=ANONYMOUS).status_code == 401


def test_an_unknown_role_is_not_authenticated():
    response = client.get("/api/v1/extraction-jobs", headers={"X-Mock-Role": "superuser"})
    assert response.status_code == 401


def test_mock_headers_are_not_honoured_outside_development(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    assert client.get("/api/v1/extraction-jobs", headers=ADMIN).status_code == 401


def test_viewer_cannot_create_correct_approve_or_finalize():
    job_id = _create()
    result_id = _first_result_id()
    body = {**BASE, "document_ids": ["DOC-001"]}
    responses = (
        client.post("/api/v1/extraction-jobs", json=body, headers=VIEWER),
        client.post(f"{_job_url(job_id)}/process", headers=VIEWER),
        client.patch(_result_url(result_id), json=FIX, headers=VIEWER),
        client.post(f"{_result_url(result_id)}/approve", headers=VIEWER),
        client.post(f"{_job_url(job_id)}/finalize", headers=VIEWER),
    )
    for response in responses:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"


def test_designer_can_create_view_and_correct_but_not_approve_or_finalize():
    job_id = _create(DESIGNER)
    result_id = _first_result_id(DESIGNER)
    assert client.get(_job_url(job_id), headers=DESIGNER).status_code == 200
    assert client.patch(_result_url(result_id), json=FIX, headers=DESIGNER).status_code == 200
    assert client.post(f"{_result_url(result_id)}/approve", headers=DESIGNER).status_code == 403
    assert client.post(f"{_job_url(job_id)}/finalize", headers=DESIGNER).status_code == 403


@pytest.mark.parametrize("headers", [OPERATOR, DESIGNER, VIEWER])
def test_only_admins_can_read_the_audit_log(headers):
    assert client.get("/api/v1/audit-logs", headers=headers).status_code == 403


def test_admin_can_read_the_audit_log():
    _create()
    assert client.get("/api/v1/audit-logs", headers=ADMIN).json()["total"] >= 1


def test_users_cannot_see_each_others_jobs():
    job_id = _create(OPERATOR)
    assert client.get(_job_url(job_id), headers=OTHER_OPERATOR).status_code == 404
    assert client.get(f"{_job_url(job_id)}/results", headers=OTHER_OPERATOR).status_code == 404
    assert client.get("/api/v1/extraction-jobs", headers=OTHER_OPERATOR).json()["total"] == 0
    assert client.get("/api/v1/extraction-jobs", headers=OPERATOR).json()["total"] == 1


def test_users_cannot_review_each_others_results():
    _create(OPERATOR)
    result_id = _first_result_id(OPERATOR)
    assert client.get("/api/v1/extraction-results", headers=OTHER_OPERATOR).json() == []
    responses = (
        client.get(_result_url(result_id), headers=OTHER_OPERATOR),
        client.patch(_result_url(result_id), json=FIX, headers=OTHER_OPERATOR),
        client.post(f"{_result_url(result_id)}/approve", headers=OTHER_OPERATOR),
    )
    for response in responses:
        assert response.status_code == 404

    detail = client.get(_result_url(result_id), headers=OPERATOR).json()  # the owner's data is untouched
    supplier = next(f for f in detail["fields"] if f["field_id"] == "supplier_name")
    assert detail["review_status"] == "pending_review" and supplier["status"] == "missing"


def test_users_cannot_start_or_finalize_each_others_jobs():
    waiting = _create(OPERATOR, ids=("DOC-001",), start=False)
    assert client.post(f"{_job_url(waiting)}/process", headers=OTHER_OPERATOR).status_code == 404
    assert client.get(_job_url(waiting), headers=OPERATOR).json()["status"] == "queued"

    finished = _create(OPERATOR, ids=("DOC-001",))
    assert client.post(f"{_job_url(finished)}/finalize", headers=OTHER_OPERATOR).status_code == 404
    assert client.get(_job_url(finished), headers=OPERATOR).json()["status"] == "review_required"


def test_finalized_results_are_scoped_to_the_owner():
    _create(OPERATOR, ids=("DOC-001",))  # a clean result is finalized automatically
    assert len(client.get("/api/v1/finalized-results", headers=OPERATOR).json()) == 1
    assert client.get("/api/v1/finalized-results", headers=OTHER_OPERATOR).json() == []
    assert len(client.get("/api/v1/finalized-results", headers=ADMIN).json()) == 1


def test_admin_can_see_and_manage_everyone_elses_work():
    job_id = _create(OPERATOR)
    result_id = _first_result_id(ADMIN)
    assert client.patch(_result_url(result_id), json=FIX, headers=ADMIN).status_code == 200
    assert client.post(f"{_result_url(result_id)}/approve", headers=ADMIN).status_code == 200
    response = client.post(f"{_job_url(job_id)}/finalize", headers=ADMIN)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_a_viewer_sees_nothing_until_sharing_is_defined():
    _create(OPERATOR)
    assert client.get("/api/v1/extraction-jobs", headers=VIEWER).json()["total"] == 0
    assert client.get("/api/v1/extraction-results", headers=VIEWER).json() == []


def test_access_denied_looks_the_same_as_not_found():
    job_id = _create(OPERATOR)
    denied = client.get(_job_url(job_id), headers=OTHER_OPERATOR)
    missing = client.get(_job_url(ZERO_ID), headers=OTHER_OPERATOR)
    assert denied.status_code == missing.status_code == 404
    assert denied.json()["error"]["code"] == missing.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert denied.json()["error"]["message"] == missing.json()["error"]["message"]


def test_role_is_checked_before_existence():
    assert client.post(f"{_job_url(ZERO_ID)}/finalize", headers=VIEWER).status_code == 403


def test_results_remember_their_owner():
    _create(OPERATOR, ids=("DOC-001",))
    assert get_db().extraction_results.find_one({})["created_by"] == "user_001"


def test_the_actor_in_the_audit_log_is_the_authenticated_user():
    job_id = _create(OTHER_OPERATOR, ids=("DOC-001",), start=False)
    page = client.get("/api/v1/audit-logs", params={"job_id": job_id}, headers=ADMIN).json()
    assert page["items"][0]["actor_user_id"] == "user_002"