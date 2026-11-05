import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _create(ids=("DOC-001",)):
    body = {"name": "T", "priority": "high", "document_ids": list(ids)}
    return client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]


def _log(**params):
    return client.get("/api/v1/audit-log", params=params).json()


def _fix_supplier(result_id, value="ABC Traders"):
    body = {"corrections": [{"field_id": "supplier_name", "value": value}]}
    return client.patch(f"/api/v1/extraction-results/{result_id}", json=body)


def _result_id():
    return client.get("/api/v1/extraction-results").json()[0]["result_id"]


def test_job_creation_writes_one_audit_entry():
    job_id = _create(["DOC-001", "DOC-002"])
    page = _log()
    assert page["total"] == 1
    entry = page["items"][0]
    assert entry["action"] == "job.created"
    assert entry["user_id"] == "user_001"
    assert entry["timestamp"] is not None
    assert entry["entity_id"] == job_id
    assert entry["details"]["document_count"] == 2


def test_start_processing_is_audited_once():
    job_id = _create()
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")  # rejected with 409
    started = _log(action="job.processing_started")
    assert started["total"] == 1


def test_correction_records_user_action_timestamp_and_before_after():  # US-11 AC2
    job_id = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    _fix_supplier(_result_id())
    entry = _log(action="review.fields_corrected")["items"][0]
    assert entry["user_id"] == "user_001"
    assert entry["timestamp"] is not None
    assert entry["details"]["changes"] == {"supplier_name": {"from": None, "to": "ABC Traders"}}


def test_second_correction_shows_the_previous_correction_as_from():
    job_id = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    result_id = _result_id()
    _fix_supplier(result_id, "ABC Traders")
    _fix_supplier(result_id, "XYZ Ltd")
    newest = _log(action="review.fields_corrected")["items"][0]
    assert newest["details"]["changes"]["supplier_name"] == {"from": "ABC Traders", "to": "XYZ Ltd"}


def test_finalizing_is_audited_with_corrected_fields():
    job_id = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    result_id = _result_id()
    _fix_supplier(result_id)
    client.post(f"/api/v1/extraction-results/{result_id}/approve")
    entry = _log(action="review.result_approved")["items"][0]
    assert entry["entity_id"] == result_id
    assert entry["details"]["corrected_fields"] == ["supplier_name"]


def test_rejected_requests_write_no_audit_entry():
    job_id = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    result_id = _result_id()
    before = _log()["total"]  # create + process = 2

    bad_field = {"corrections": [{"field_id": "banana", "value": "x"}]}
    assert client.patch(f"/api/v1/extraction-results/{result_id}", json=bad_field).status_code == 422
    assert client.post(f"/api/v1/extraction-results/{result_id}/approve").status_code == 422  # supplier empty
    assert _fix_supplier("REV-NOPE").status_code == 404
    assert client.post(f"/api/v1/extraction-jobs/{job_id}/process").status_code == 409

    assert _log()["total"] == before


def test_read_requests_write_no_audit_entry():
    job_id = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    before = _log()["total"]
    for path in ("/api/v1/extraction-jobs", f"/api/v1/extraction-jobs/{job_id}", "/api/v1/extraction-results",
                 "/api/v1/extraction-jobs", "/api/v1/finalized-results", "/api/v1/audit-log"):
        assert client.get(path).status_code == 200
    assert _log()["total"] == before


def test_full_workflow_writes_exactly_one_entry_per_action():  # NFR 3
    job_id = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    result_id = _result_id()
    _fix_supplier(result_id)
    client.post(f"/api/v1/extraction-results/{result_id}/approve")

    entries = _log()["items"]
    assert [e["action"] for e in entries] == [
        "review.result_approved",
        "review.fields_corrected",
        "job.processing_started",
        "job.created",
    ]
    assert all(e["user_id"] == "user_001" and e["timestamp"] for e in entries)


def test_audit_log_filters():
    first = _create(["DOC-001"])
    second = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{second}/process")

    assert _log(action="job.created")["total"] == 2
    assert _log(job_id=second)["total"] == 2
    assert _log(job_id=first)["total"] == 1
    assert _log(entity_id=second)["total"] == 2
    assert _log(user_id="user_001")["total"] == 3
    assert _log(user_id="nobody")["total"] == 0
    assert client.get("/api/v1/audit-log", params={"action": "bad.action"}).status_code == 422


def test_audit_log_pagination():
    for _ in range(3):
        _create()
    first = _log(page=1, page_size=2)
    second = _log(page=2, page_size=2)
    assert first["total"] == 3 and len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert not {e["audit_id"] for e in first["items"]} & {e["audit_id"] for e in second["items"]}


@pytest.mark.parametrize("params", [{"page_size": 0}, {"page_size": 101}, {"page": 0}])
def test_page_parameters_outside_allowed_range_are_rejected(params):
    assert client.get("/api/v1/audit-log", params=params).status_code == 422


def test_audit_log_is_read_only():
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/v1/audit-log").status_code == 405