import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _process(ids):
    body = {"name": "T", "priority": "high", "document_ids": ids}
    job_id = client.post("/api/v1/jobs", json=body).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/process")
    return job_id


def _task_for(doc_id):
    tasks = client.get("/api/v1/review-tasks").json()
    return next(t for t in tasks if t["document_id"] == doc_id)


def _fix_supplier(result_id, value="ABC Traders"):
    body = {"corrections": [{"field_id": "supplier_name", "value": value}]}
    return client.patch(f"/api/v1/review-tasks/{result_id}/fields", json=body)


def _finalize(result_id):
    return client.post(f"/api/v1/review-tasks/{result_id}/finalize")


def _results(job_id=None):
    params = {"job_id": job_id} if job_id else {}
    return client.get("/api/v1/finalized-results", params=params).json()


def test_cannot_finalize_with_unresolved_required_field():
    _process(["DOC-003"])
    response = _finalize(_task_for("DOC-003")["result_id"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUIRED_FIELDS_MISSING"
    assert "supplier_name" in response.json()["error"]["message"]


def test_finalize_sets_status_approved():  # US-09 AC1
    _process(["DOC-003"])
    result_id = _task_for("DOC-003")["result_id"]
    _fix_supplier(result_id)
    response = _finalize(result_id)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["approved_by"] == "user_001"


def test_task_without_problem_fields_can_be_approved_as_is():
    _process(["DOC-005"])
    assert _finalize(_task_for("DOC-005")["result_id"]).status_code == 200


def test_approved_task_leaves_the_queue():
    _process(["DOC-003"])
    result_id = _task_for("DOC-003")["result_id"]
    _fix_supplier(result_id)
    _finalize(result_id)
    assert client.get("/api/v1/review-tasks").json() == []


def test_approved_document_appears_in_finalized_results():  # US-09 AC2
    job_id = _process(["DOC-003"])
    result_id = _task_for("DOC-003")["result_id"]
    _fix_supplier(result_id)
    _finalize(result_id)

    results = _results(job_id)
    assert len(results) == 1
    result = results[0]
    assert result["document_id"] == "DOC-003"
    assert result["review_status"] == "approved"
    assert result["finalized_by"] == "user_001"
    supplier = next(f for f in result["fields"] if f["field_id"] == "supplier_name")
    assert supplier["value"] == "ABC Traders"
    assert supplier["status"] == "corrected"


def test_results_contain_auto_passed_but_not_unreviewed_documents():
    job_id = _process(["DOC-001", "DOC-003"])
    results = _results(job_id)
    assert [r["document_id"] for r in results] == ["DOC-001"]
    assert results[0]["review_status"] == "not_required"
    assert results[0]["finalized_by"] == "system"
    assert [f["status"] for f in results[0]["fields"]] == ["extracted"] * 3

    items = client.get(f"/api/v1/jobs/{job_id}").json()["items"]
    by_doc = {i["document_id"]: i for i in items}
    assert by_doc["DOC-003"]["review_status"] == "pending_review"


def test_failed_document_is_never_in_results():
    _process(["DOC-008"])
    assert _results() == []


def test_cannot_finalize_twice():
    _process(["DOC-005"])
    result_id = _task_for("DOC-005")["result_id"]
    assert _finalize(result_id).status_code == 200
    assert _finalize(result_id).status_code == 409


def test_cannot_edit_after_finalizing():
    _process(["DOC-003"])
    result_id = _task_for("DOC-003")["result_id"]
    _fix_supplier(result_id)
    _finalize(result_id)
    assert _fix_supplier(result_id, "Other Co").status_code == 409


def test_finalize_unknown_task_returns_404():
    assert _finalize("REV-NOPE").status_code == 404


def test_results_can_be_filtered_by_job():
    first = _process(["DOC-001"])
    _process(["DOC-001"])
    assert len(_results()) == 2
    assert len(_results(first)) == 1