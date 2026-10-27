import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _create(ids=("DOC-001",)):
    body = {"name": "T", "priority": "high", "document_ids": list(ids)}
    return client.post("/batches", json=body).json()["batch_id"]


def _log(**params):
    return client.get("/audit-log", params=params).json()


def _fix_supplier(task_id, value="ABC Traders"):
    body = {"corrections": [{"name": "supplier_name", "value": value}]}
    return client.patch(f"/review-tasks/{task_id}/fields", json=body)


def _task_id():
    return client.get("/review-tasks").json()[0]["task_id"]


def test_batch_creation_writes_one_audit_entry():
    batch_id = _create(["DOC-001", "DOC-002"])
    page = _log()
    assert page["total"] == 1
    entry = page["items"][0]
    assert entry["action"] == "batch.created"
    assert entry["user_id"] == "user_001"
    assert entry["timestamp"] is not None
    assert entry["entity_id"] == batch_id
    assert entry["details"]["document_count"] == 2


def test_start_processing_is_audited_once():
    batch_id = _create()
    client.post(f"/batches/{batch_id}/process")
    client.post(f"/batches/{batch_id}/process")  # rejected with 409
    started = _log(action="batch.processing_started")
    assert started["total"] == 1


def test_correction_records_user_action_timestamp_and_before_after():  # US-11 AC2
    batch_id = _create(["DOC-003"])
    client.post(f"/batches/{batch_id}/process")
    _fix_supplier(_task_id())
    entry = _log(action="review.fields_corrected")["items"][0]
    assert entry["user_id"] == "user_001"
    assert entry["timestamp"] is not None
    assert entry["details"]["changes"] == {"supplier_name": {"from": None, "to": "ABC Traders"}}


def test_second_correction_shows_the_previous_correction_as_from():
    batch_id = _create(["DOC-003"])
    client.post(f"/batches/{batch_id}/process")
    task_id = _task_id()
    _fix_supplier(task_id, "ABC Traders")
    _fix_supplier(task_id, "XYZ Ltd")
    newest = _log(action="review.fields_corrected")["items"][0]
    assert newest["details"]["changes"]["supplier_name"] == {"from": "ABC Traders", "to": "XYZ Ltd"}


def test_finalizing_is_audited_with_corrected_fields():
    batch_id = _create(["DOC-003"])
    client.post(f"/batches/{batch_id}/process")
    task_id = _task_id()
    _fix_supplier(task_id)
    client.post(f"/review-tasks/{task_id}/finalize")
    entry = _log(action="review.task_approved")["items"][0]
    assert entry["entity_id"] == task_id
    assert entry["details"]["corrected_fields"] == ["supplier_name"]


def test_rejected_requests_write_no_audit_entry():
    batch_id = _create(["DOC-003"])
    client.post(f"/batches/{batch_id}/process")
    task_id = _task_id()
    before = _log()["total"]  # create + process = 2

    bad_field = {"corrections": [{"name": "banana", "value": "x"}]}
    assert client.patch(f"/review-tasks/{task_id}/fields", json=bad_field).status_code == 422
    assert client.post(f"/review-tasks/{task_id}/finalize").status_code == 422  # supplier empty
    assert _fix_supplier("REV-NOPE").status_code == 404
    assert client.post(f"/batches/{batch_id}/process").status_code == 409

    assert _log()["total"] == before


def test_read_requests_write_no_audit_entry():
    batch_id = _create(["DOC-003"])
    client.post(f"/batches/{batch_id}/process")
    before = _log()["total"]
    for path in ("/batches", f"/batches/{batch_id}", "/review-tasks",
                 "/job-history", "/finalized-results", "/audit-log"):
        assert client.get(path).status_code == 200
    assert _log()["total"] == before


def test_full_workflow_writes_exactly_one_entry_per_action():  # NFR 3
    batch_id = _create(["DOC-003"])
    client.post(f"/batches/{batch_id}/process")
    task_id = _task_id()
    _fix_supplier(task_id)
    client.post(f"/review-tasks/{task_id}/finalize")

    entries = _log()["items"]
    assert [e["action"] for e in entries] == [
        "review.task_approved",
        "review.fields_corrected",
        "batch.processing_started",
        "batch.created",
    ]
    assert all(e["user_id"] == "user_001" and e["timestamp"] for e in entries)


def test_audit_log_filters():
    first = _create(["DOC-001"])
    second = _create(["DOC-003"])
    client.post(f"/batches/{second}/process")

    assert _log(action="batch.created")["total"] == 2
    assert _log(batch_id=second)["total"] == 2
    assert _log(batch_id=first)["total"] == 1
    assert _log(entity_id=second)["total"] == 2
    assert _log(user_id="user_001")["total"] == 3
    assert _log(user_id="nobody")["total"] == 0
    assert client.get("/audit-log", params={"action": "bad.action"}).status_code == 422


def test_audit_log_pagination():
    for _ in range(3):
        _create()
    first = _log(limit=2, offset=0)
    second = _log(limit=2, offset=2)
    assert first["total"] == 3 and len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert not {e["audit_id"] for e in first["items"]} & {e["audit_id"] for e in second["items"]}


@pytest.mark.parametrize("limit", [0, 201])
def test_limit_outside_allowed_range_is_rejected(limit):
    assert client.get("/audit-log", params={"limit": limit}).status_code == 422


def test_audit_log_is_read_only():
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/audit-log").status_code == 405