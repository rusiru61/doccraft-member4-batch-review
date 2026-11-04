from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from bson import ObjectId

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
TEN_DOCS = [f"DOC-{n:03d}" for n in range(1, 11)]


def _create(ids=("DOC-001",), name="T"):
    body = {"name": name, "priority": "high", "document_ids": list(ids)}
    return client.post("/api/v1/jobs", json=body).json()["job_id"]


def _history(**params):
    return client.get("/api/v1/job-history", params=params).json()


def test_creation_event_is_recorded():  # US-11 AC1
    job_id = _create()
    page = _history()
    entry = page["items"][0]
    assert entry["job_id"] == job_id
    assert entry["status"] == "pending"
    assert entry["created_by"] == "user_001"
    assert entry["created_at"] is not None
    assert entry["started_at"] is None and entry["duration_seconds"] is None


def test_processed_job_shows_counts_and_duration():
    job_id = _create(TEN_DOCS)
    client.post(f"/api/v1/jobs/{job_id}/process")
    entry = _history()["items"][0]
    assert entry["status"] == "completed"
    assert (entry["total"], entry["completed"], entry["failed"]) == (10, 9, 1)
    assert entry["pending_review"] == 3
    assert entry["started_at"] is not None and entry["completed_at"] is not None
    assert entry["duration_seconds"] >= 0


def test_history_is_newest_first():
    older = _create(name="older")
    get_db().extraction_jobs.update_one(
        {"_id": ObjectId(older)},
        {"$set": {"created_at": datetime(2020, 1, 1, tzinfo=timezone.utc)}},
    )
    newer = _create(name="newer")
    assert [e["job_id"] for e in _history()["items"]] == [newer, older]


def test_history_can_be_filtered_by_status():
    pending = _create(name="pending")
    done = _create(["DOC-001"], name="done")
    client.post(f"/api/v1/jobs/{done}/process")
    assert [e["job_id"] for e in _history(status="completed")["items"]] == [done]
    assert [e["job_id"] for e in _history(status="pending")["items"]] == [pending]


def test_pagination_returns_slices_and_total():
    for n in range(3):
        _create(name=f"b{n}")
    first = _history(page=1, page_size=2)
    second = _history(page=2, page_size=2)
    assert first["total"] == 3 and len(first["items"]) == 2
    assert (first["page"], first["page_size"]) == (1, 2)
    assert len(second["items"]) == 1
    assert not {e["job_id"] for e in first["items"]} & {e["job_id"] for e in second["items"]}


@pytest.mark.parametrize("params", [{"page_size": 0}, {"page_size": 101}, {"page": 0}])
def test_page_parameters_outside_allowed_range_are_rejected(params):
    assert client.get("/api/v1/job-history", params=params).status_code == 422


def test_pending_review_count_drops_after_approval():
    job_id = _create(["DOC-005"])
    client.post(f"/api/v1/jobs/{job_id}/process")
    assert _history()["items"][0]["pending_review"] == 1
    result_id = client.get("/api/v1/review-tasks").json()[0]["result_id"]
    client.post(f"/api/v1/review-tasks/{result_id}/finalize")
    assert _history()["items"][0]["pending_review"] == 0


def test_empty_history():
    page = _history()
    assert page["total"] == 0 and page["items"] == []