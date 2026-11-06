import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
TEN_DOCS = [f"DOC-{n:03d}" for n in range(1, 11)]


def _process(ids):
    body = {"name": "T", "priority": "high", "template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE", "start": False, "document_ids": list(ids)}
    job_id = client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    return job_id


def _results(**params):
    return client.get("/api/v1/extraction-results", params=params).json()


def test_queue_defaults_to_pending_review_lowest_score_first():
    _process(TEN_DOCS)
    results = _results()
    assert [r["document_id"] for r in results] == ["DOC-003", "DOC-006", "DOC-005"]
    assert {r["review_status"] for r in results} == {"pending_review"}


def test_results_can_be_listed_by_review_status():
    _process(TEN_DOCS)
    assert len(_results(review_status="not_required")) == 6
    assert len(_results(review_status="pending_review")) == 3
    assert _results(review_status="approved") == []


def test_results_can_be_filtered_by_job():
    first = _process(["DOC-003"])
    _process(["DOC-006"])
    assert len(_results()) == 2
    assert [r["document_id"] for r in _results(job_id=first)] == ["DOC-003"]
    assert _results(job_id="JOB-NOPE") == []


def test_invalid_review_status_is_rejected():
    response = client.get("/api/v1/extraction-results", params={"review_status": "banana"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a_result_that_needs_no_review_can_be_viewed_but_not_edited():
    _process(["DOC-001"])
    result = _results(review_status="not_required")[0]
    detail = client.get(f"/api/v1/extraction-results/{result['result_id']}")
    assert detail.status_code == 200
    assert detail.json()["review_status"] == "not_required"

    fix = {"corrections": [{"field_id": "supplier_name", "value": "X"}]}
    response = client.patch(f"/api/v1/extraction-results/{result['result_id']}", json=fix)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEW_NOT_PENDING"


def test_a_failed_result_has_no_extraction_to_view():
    job_id = _process(["DOC-008"])
    job = client.get(f"/api/v1/extraction-jobs/{job_id}").json()
    failed_id = job["items"][0]["result_id"]
    assert client.get(f"/api/v1/extraction-results/{failed_id}").status_code == 404


def test_approving_records_the_reviewer():
    _process(["DOC-005"])
    result = _results()[0]
    response = client.post(f"/api/v1/extraction-results/{result['result_id']}/approve")
    body = response.json()
    assert response.status_code == 200
    assert body["review_status"] == "approved"
    assert body["reviewed_by"] == "user_001"
    assert body["reviewed_at"] is not None
    assert _results() == []


def test_results_expose_only_the_new_names():
    _process(["DOC-003"])
    result = _results()[0]
    assert {"result_id", "job_id", "review_status"} <= set(result)
    assert not {"task_id", "item_id", "batch_id", "status"} & set(result)


def test_job_and_result_payloads_use_the_new_names():
    job_id = _process(["DOC-003"])
    job = client.get(f"/api/v1/extraction-jobs/{job_id}").json()
    assert "job_id" in job and "batch_id" not in job
    assert {"result_id", "job_id"} <= set(job["items"][0])
    assert not {"item_id", "batch_id"} & set(job["items"][0])