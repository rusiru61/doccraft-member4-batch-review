import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.review_service import build_final_fields

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _process(ids):
    body = {"name": "T", "priority": "high", "document_ids": ids}
    batch_id = client.post("/batches", json=body).json()["batch_id"]
    client.post(f"/batches/{batch_id}/process")
    return batch_id


def _task_for(doc_id):
    return next(t for t in client.get("/review-tasks").json() if t["document_id"] == doc_id)


def _fix_supplier(task_id, value="ABC Traders"):
    body = {"corrections": [{"name": "supplier_name", "value": value}]}
    return client.patch(f"/review-tasks/{task_id}/fields", json=body)


def _finalize(task_id):
    return client.post(f"/review-tasks/{task_id}/finalize")


def _results(batch_id=None):
    params = {"batch_id": batch_id} if batch_id else {}
    return client.get("/finalized-results", params=params).json()


def test_build_final_fields_prefers_corrections():
    extraction = {"fields": [{"name": "a", "value": None}, {"name": "b", "value": "x"}]}
    corrections = {"a": {"value": "fixed"}}
    assert build_final_fields(extraction, corrections) == [
        {"name": "a", "value": "fixed", "corrected": True},
        {"name": "b", "value": "x", "corrected": False},
    ]


def test_cannot_finalize_with_empty_required_field():
    _process(["DOC-003"])
    response = _finalize(_task_for("DOC-003")["task_id"])
    assert response.status_code == 422
    assert "supplier_name" in response.json()["detail"]


def test_finalize_sets_status_approved():  # US-09 AC1
    _process(["DOC-003"])
    task_id = _task_for("DOC-003")["task_id"]
    _fix_supplier(task_id)
    response = _finalize(task_id)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["approved_by"] == "user_001"


def test_task_without_missing_fields_can_be_approved_as_is():
    _process(["DOC-005"])
    assert _finalize(_task_for("DOC-005")["task_id"]).status_code == 200


def test_approved_task_leaves_the_queue():
    _process(["DOC-003"])
    task_id = _task_for("DOC-003")["task_id"]
    _fix_supplier(task_id)
    _finalize(task_id)
    assert client.get("/review-tasks").json() == []


def test_approved_document_appears_in_finalized_results():  # US-09 AC2
    batch_id = _process(["DOC-003"])
    task_id = _task_for("DOC-003")["task_id"]
    _fix_supplier(task_id)
    _finalize(task_id)

    results = _results(batch_id)
    assert len(results) == 1
    result = results[0]
    assert result["document_id"] == "DOC-003"
    assert result["review_status"] == "approved"
    assert result["finalized_by"] == "user_001"
    supplier = next(f for f in result["fields"] if f["name"] == "supplier_name")
    assert supplier["value"] == "ABC Traders"
    assert supplier["corrected"] is True


def test_results_contain_auto_passed_but_not_unreviewed_documents():
    batch_id = _process(["DOC-001", "DOC-003"])
    results = _results(batch_id)
    assert [r["document_id"] for r in results] == ["DOC-001"]
    assert results[0]["review_status"] == "not_required"
    assert results[0]["finalized_by"] == "system"

    items = {i["document_id"]: i for i in client.get(f"/batches/{batch_id}").json()["items"]}
    assert items["DOC-003"]["review_status"] == "pending_review"


def test_failed_document_is_never_in_results():
    _process(["DOC-008"])
    assert _results() == []


def test_cannot_finalize_twice():
    _process(["DOC-005"])
    task_id = _task_for("DOC-005")["task_id"]
    assert _finalize(task_id).status_code == 200
    assert _finalize(task_id).status_code == 409


def test_cannot_edit_after_finalizing():
    _process(["DOC-003"])
    task_id = _task_for("DOC-003")["task_id"]
    _fix_supplier(task_id)
    _finalize(task_id)
    assert _fix_supplier(task_id, "Other Co").status_code == 409


def test_finalize_unknown_task_returns_404():
    assert _finalize("REV-NOPE").status_code == 404


def test_results_can_be_filtered_by_batch():
    first = _process(["DOC-001"])
    _process(["DOC-001"])
    assert len(_results()) == 2
    assert len(_results(first)) == 1