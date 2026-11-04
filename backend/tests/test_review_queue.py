import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.services.review_service import needs_review

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
TEN_DOCS = [f"DOC-{n:03d}" for n in range(1, 11)]


def _processed_batch(ids):
    body = {"name": "T", "priority": "high", "document_ids": ids}
    batch_id = client.post("/api/v1/batches", json=body).json()["batch_id"]
    client.post(f"/api/v1/batches/{batch_id}/process")
    return batch_id


@pytest.mark.parametrize("score, expected", [(0.79, True), (0.80, False), (0.95, False)])
def test_needs_review_threshold_boundary(score, expected):  # US-06 AC1, AC2
    assert needs_review(score) is expected


def test_scores_are_stored_on_items():  # US-05 in the real flow
    batch_id = _processed_batch(["DOC-001", "DOC-003"])
    items = {i["document_id"]: i for i in client.get(f"/api/v1/batches/{batch_id}").json()["items"]}
    assert items["DOC-001"]["reliability_score"] == pytest.approx(0.9643, abs=1e-4)
    assert items["DOC-003"]["reliability_score"] == pytest.approx(0.41)


def test_queue_is_sorted_lowest_score_first():  # US-07 AC3
    _processed_batch(TEN_DOCS)
    tasks = client.get("/api/v1/review-tasks").json()
    assert [t["document_id"] for t in tasks] == ["DOC-003", "DOC-006", "DOC-005"]
    assert [t["reliability_score"] for t in tasks] == pytest.approx([0.41, 0.50, 0.77])


def test_high_scoring_documents_create_no_review_task():
    _processed_batch(["DOC-001", "DOC-002"])
    assert client.get("/api/v1/review-tasks").json() == []


def test_failed_document_creates_no_review_task():
    _processed_batch(["DOC-008"])
    assert client.get("/api/v1/review-tasks").json() == []


def test_queue_shows_only_pending_tasks():  # US-07 AC2
    _processed_batch(TEN_DOCS)
    get_db().extraction_results.update_one(
        {"document_id": "DOC-003"}, {"$set": {"review_status": "approved"}}
    )
    tasks = client.get("/api/v1/review-tasks").json()
    assert [t["document_id"] for t in tasks] == ["DOC-006", "DOC-005"]