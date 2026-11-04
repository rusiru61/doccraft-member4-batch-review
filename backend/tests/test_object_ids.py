import re

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.ids import to_object_id
from app.integrations.data_structure_provider import MockDataStructureProvider
from app.integrations.extraction_service import MockExtractionService
from app.main import app
from app.services.review_service import decide_review

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
TEN_DOCS = [f"DOC-{n:03d}" for n in range(1, 11)]
DEFINITIONS = MockDataStructureProvider().get_field_definitions()


def _create(ids):
    body = {"name": "T", "priority": "high", "document_ids": list(ids)}
    return client.post("/api/v1/jobs", json=body).json()["job_id"]


def _process(ids):
    job_id = _create(ids)
    client.post(f"/api/v1/jobs/{job_id}/process")
    return job_id


def test_to_object_id_accepts_only_valid_ids():
    valid = str(ObjectId())
    assert to_object_id(valid) == ObjectId(valid)
    for bad in ("", "JOB-NOPE", "12345", "z" * 24, "a" * 23, None, 123):
        assert to_object_id(bad) is None


def test_public_ids_are_object_id_strings():
    job_id = _process(["DOC-003"])
    item = client.get(f"/api/v1/jobs/{job_id}").json()["items"][0]
    task = client.get("/api/v1/review-tasks").json()[0]
    for value in (job_id, item["result_id"], task["result_id"]):
        assert re.fullmatch(r"[0-9a-f]{24}", value)
    assert item["result_id"] == task["result_id"]  # one result is both the item and its review task
    assert item["job_id"] == job_id


def test_malformed_and_unknown_ids_return_404_not_500():
    for bad in ("JOB-NOPE", "0" * 24):
        assert client.get(f"/api/v1/jobs/{bad}").status_code == 404
        assert client.post(f"/api/v1/jobs/{bad}/process").status_code == 404
        assert client.get(f"/api/v1/review-tasks/{bad}").status_code == 404
        assert client.post(f"/api/v1/review-tasks/{bad}/finalize").status_code == 404


def test_results_are_stored_in_one_collection():
    job_id = _process(TEN_DOCS)
    results = get_db().extraction_results
    assert results.count_documents({"job_id": ObjectId(job_id)}) == 10
    assert results.count_documents({"review_status": "pending_review"}) == 3
    assert get_db().extraction_jobs.count_documents({}) == 1


def test_only_the_team_collections_are_used():
    _process(["DOC-003"])
    names = set(get_db().list_collection_names())
    assert {"extraction_jobs", "extraction_results", "audit_logs"} <= names
    assert not names & {"jobs", "job_items", "review_tasks", "audit_log"}


def test_every_completed_result_has_a_review_decision():
    _process(TEN_DOCS)
    results = get_db().extraction_results
    assert results.count_documents({"status": "completed"}) == 9
    assert results.count_documents({"status": "completed", "review_status": {"$exists": False}}) == 0
    assert results.count_documents({"status": "failed", "review_status": {"$exists": True}}) == 0


def test_decide_review_auto_finalizes_a_clean_high_score():
    result = MockExtractionService().extract("DOC-001")
    decision = decide_review(result, DEFINITIONS, 0.96)
    assert decision["review_status"] == "not_required"
    assert decision["finalized_by"] == "system"
    assert [f["status"] for f in decision["final_fields"]] == ["extracted"] * 3


def test_decide_review_flags_a_low_score():
    result = MockExtractionService().extract("DOC-001")
    decision = decide_review(result, DEFINITIONS, 0.5)
    assert decision["review_status"] == "pending_review"
    assert decision["review_reasons"] == ["low_reliability"]
    assert "final_fields" not in decision


def test_decide_review_flags_a_required_problem_even_with_a_perfect_score():
    result = MockExtractionService().extract("DOC-003")
    decision = decide_review(result, DEFINITIONS, 1.0)
    assert decision["review_reasons"] == ["required_field_problem"]
    assert decision["flagged_fields"] == ["supplier_name"]


def test_a_result_that_needs_no_review_is_not_a_task():
    job_id = _process(["DOC-001"])
    result_id = client.get(f"/api/v1/jobs/{job_id}").json()["items"][0]["result_id"]
    assert client.get(f"/api/v1/review-tasks/{result_id}").status_code == 404
    assert client.get("/api/v1/review-tasks", params={"status": "approved"}).json() == []


def test_finalized_results_for_an_unknown_job_is_empty():
    response = client.get("/api/v1/finalized-results", params={"job_id": "JOB-NOPE"})
    assert response.status_code == 200 and response.json() == []