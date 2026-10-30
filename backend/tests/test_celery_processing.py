import pytest
from fastapi.testclient import TestClient

from app.core.celery_app import celery_app
from app.core.database import get_db
from app.integrations.extraction_service import MockExtractionService
from app.integrations.ocr_service import MockOcrService
from app.main import app
from app.services import processing_service
from app.services.processing_service import QueueUnavailableError
from app.tasks import processing_tasks  # noqa: F401  (importing registers the task)

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _create(ids):
    body = {"name": "T", "priority": "high", "document_ids": ids}
    return client.post("/batches", json=body).json()["batch_id"]


def test_task_is_registered_with_safe_settings():
    assert "batches.process" in celery_app.tasks
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_serializer == "json"


def test_queue_outage_returns_503_and_leaves_batch_pending(monkeypatch):
    batch_id = _create(["DOC-001"])

    def broken_queue(failed_batch_id):
        raise QueueUnavailableError(failed_batch_id)

    with monkeypatch.context() as patch:
        patch.setattr("app.api.batches.enqueue_batch_processing", broken_queue)
        assert client.post(f"/batches/{batch_id}/process").status_code == 503

    assert client.get(f"/batches/{batch_id}").json()["status"] == "pending"
    started = client.get("/audit-log", params={"action": "batch.processing_started"}).json()
    assert started["total"] == 0  # nothing happened, so nothing is audited

    # Once the queue is back, the same batch can be started normally.
    assert client.post(f"/batches/{batch_id}/process").status_code == 202
    assert client.get(f"/batches/{batch_id}").json()["status"] == "completed"


def test_resumed_processing_skips_finished_items():
    batch_id = _create(["DOC-001", "DOC-002", "DOC-004"])
    db = get_db()
    # Simulate a worker that stopped half way: DOC-001 finished, DOC-002 was mid-processing.
    db.batches.update_one({"batch_id": batch_id}, {"$set": {"status": "processing"}})
    db.job_items.update_one(
        {"batch_id": batch_id, "document_id": "DOC-001"},
        {"$set": {"status": "completed", "reliability_score": 0.123}},
    )
    db.job_items.update_one(
        {"batch_id": batch_id, "document_id": "DOC-002"}, {"$set": {"status": "processing"}}
    )

    processing_service.process_batch(batch_id, MockExtractionService(), MockOcrService())

    detail = client.get(f"/batches/{batch_id}").json()
    items = {i["document_id"]: i for i in detail["items"]}
    assert detail["status"] == "completed"
    assert items["DOC-001"]["reliability_score"] == 0.123  # untouched: not reprocessed
    assert items["DOC-002"]["status"] == "completed"
    assert items["DOC-004"]["status"] == "completed"


def test_running_a_finished_batch_again_changes_nothing():
    batch_id = _create(["DOC-003"])
    client.post(f"/batches/{batch_id}/process")
    before = client.get(f"/batches/{batch_id}").json()["items"]

    processing_service.process_batch(batch_id, MockExtractionService(), MockOcrService())

    assert client.get(f"/batches/{batch_id}").json()["items"] == before
    assert get_db().review_tasks.count_documents({}) == 1