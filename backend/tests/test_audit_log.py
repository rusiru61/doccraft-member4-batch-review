import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
ADMIN = {"X-Mock-User-Id": "admin_1", "X-Mock-Role": "admin"}
BASE = {"template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE"}
FIX = {"corrections": [{"field_id": "supplier_name", "value": "ABC Traders"}]}
ENTRY_KEYS = {
    "audit_id", "timestamp", "actor_user_id", "action", "resource_type",
    "resource_id", "job_id", "changed_fields", "safe_metadata",
}


def _create(ids=("DOC-001",), start=False):
    body = {**BASE, "document_ids": list(ids), "start": start}
    return client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]


def _log(**params):
    return client.get("/api/v1/audit-logs", params=params, headers=ADMIN).json()


def _first_result_id():
    return client.get("/api/v1/extraction-results").json()[0]["result_id"]


def test_job_creation_writes_one_audit_entry():
    job_id = _create(["DOC-001", "DOC-002"])
    page = _log()
    assert page["total"] == 1
    entry = page["items"][0]
    assert entry["action"] == "job.created"
    assert entry["actor_user_id"] == "user_001"
    assert entry["timestamp"] is not None
    assert (entry["resource_type"], entry["resource_id"], entry["job_id"]) == (
        "extraction_job", job_id, job_id,
    )
    assert entry["safe_metadata"]["document_count"] == 2


def test_starting_a_job_is_audited_once():
    job_id = _create()
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")  # rejected with 409
    assert _log(action="job.processing_started")["total"] == 1


def test_creating_and_starting_in_one_call_writes_two_entries():
    _create(start=True)
    assert [e["action"] for e in _log()["items"]] == ["job.processing_started", "job.created"]


def test_correction_records_actor_action_timestamp_and_changed_fields():  # US-11 AC2
    _create(["DOC-003"], start=True)
    result_id = _first_result_id()
    client.patch(f"/api/v1/extraction-results/{result_id}", json=FIX)
    entry = _log(action="review.fields_corrected")["items"][0]
    assert entry["actor_user_id"] == "user_001"
    assert entry["timestamp"] is not None
    assert entry["resource_id"] == result_id
    assert entry["changed_fields"] == ["supplier_name"]
    assert entry["safe_metadata"] == {"document_id": "DOC-003"}


def test_audit_entries_never_contain_the_corrected_values():
    _create(["DOC-003"], start=True)
    client.patch(f"/api/v1/extraction-results/{_first_result_id()}", json=FIX)
    assert "ABC Traders" not in str(_log()["items"])


def test_approval_is_audited_with_the_corrected_fields():
    _create(["DOC-003"], start=True)
    result_id = _first_result_id()
    client.patch(f"/api/v1/extraction-results/{result_id}", json=FIX)
    client.post(f"/api/v1/extraction-results/{result_id}/approve")
    entry = _log(action="review.result_approved")["items"][0]
    assert entry["resource_id"] == result_id
    assert entry["changed_fields"] == ["supplier_name"]


def test_rejected_requests_write_no_audit_entry():
    job_id = _create(["DOC-003"], start=True)
    result_id = _first_result_id()
    before = _log()["total"]  # created + started = 2

    bad = {"corrections": [{"field_id": "banana", "value": "x"}]}
    assert client.patch(f"/api/v1/extraction-results/{result_id}", json=bad).status_code == 422
    assert client.post(f"/api/v1/extraction-results/{result_id}/approve").status_code == 422
    assert client.patch(f"/api/v1/extraction-results/{'0' * 24}", json=FIX).status_code == 404
    assert client.post(f"/api/v1/extraction-jobs/{job_id}/process").status_code == 409
    assert client.post(f"/api/v1/extraction-jobs/{job_id}/finalize").status_code == 409

    assert _log()["total"] == before


def test_read_requests_write_no_audit_entry():
    job_id = _create(["DOC-003"], start=True)
    before = _log()["total"]
    for path in (
        "/api/v1/extraction-jobs",
        f"/api/v1/extraction-jobs/{job_id}",
        f"/api/v1/extraction-jobs/{job_id}/results",
        "/api/v1/extraction-results",
        "/api/v1/finalized-results",
        "/api/v1/audit-logs",
    ):
        assert client.get(path, headers=ADMIN).status_code == 200
    assert _log()["total"] == before


def test_full_workflow_writes_exactly_one_entry_per_action():  # NFR 3
    job_id = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    result_id = _first_result_id()
    client.patch(f"/api/v1/extraction-results/{result_id}", json=FIX)
    client.post(f"/api/v1/extraction-results/{result_id}/approve")
    assert client.post(f"/api/v1/extraction-jobs/{job_id}/finalize").status_code == 200

    entries = _log()["items"]
    assert [e["action"] for e in entries] == [
        "job.finalized",
        "review.result_approved",
        "review.fields_corrected",
        "job.processing_started",
        "job.created",
    ]
    assert all(e["actor_user_id"] == "user_001" and e["timestamp"] for e in entries)


def test_audit_log_filters():
    first = _create(["DOC-001"])
    second = _create(["DOC-003"])
    client.post(f"/api/v1/extraction-jobs/{second}/process")

    assert _log(action="job.created")["total"] == 2
    assert _log(job_id=second)["total"] == 2
    assert _log(job_id=first)["total"] == 1
    assert _log(resource_id=second)["total"] == 2
    assert _log(resource_type="extraction_job")["total"] == 3
    assert _log(actor_user_id="user_001")["total"] == 3
    assert _log(actor_user_id="nobody")["total"] == 0
    bad = client.get("/api/v1/audit-logs", params={"action": "bad.action"}, headers=ADMIN)
    assert bad.status_code == 422


def test_audit_log_pagination():
    for _ in range(3):
        _create()
    first = _log(page=1, page_size=2)
    second = _log(page=2, page_size=2)
    assert first["total"] == 3 and len(first["items"]) == 2
    assert (first["page"], first["page_size"]) == (1, 2)
    assert len(second["items"]) == 1
    assert not {e["audit_id"] for e in first["items"]} & {e["audit_id"] for e in second["items"]}


@pytest.mark.parametrize("params", [{"page_size": 0}, {"page_size": 101}, {"page": 0}])
def test_page_parameters_outside_allowed_range_are_rejected(params):
    assert client.get("/api/v1/audit-logs", params=params, headers=ADMIN).status_code == 422


def test_audit_log_is_read_only():
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/api/v1/audit-logs", headers=ADMIN).status_code == 405


def test_audit_entries_use_the_team_field_names():
    _create()
    entry = _log()["items"][0]
    assert set(entry) == ENTRY_KEYS
    assert len(entry["audit_id"]) == 24