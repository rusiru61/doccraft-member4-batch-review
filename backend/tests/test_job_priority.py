import pytest
from fastapi.testclient import TestClient

from app.core.celery_app import celery_app, queue_for_priority
from app.integrations.auth_service import CurrentUser
from app.integrations.extraction_service import MockExtractionService
from app.integrations.ocr_service import MockOcrService
from app.main import app
from app.services import processing_service
from app.tasks import processing_tasks

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
USER = CurrentUser(user_id="user_001", role="operator")


def _create(priority="medium"):
    body = {"name": "T", "priority": priority, "document_ids": ["DOC-001"]}
    return client.post("/batches", json=body).json()["batch_id"]


class _FakeTask:
    def __init__(self):
        self.sent = []

    def apply_async(self, args, queue):
        self.sent.append((args, queue))


@pytest.mark.parametrize(
    "priority, queue",
    [("high", "p1_high"), ("medium", "p2_medium"), ("low", "p3_low"), ("urgent", "p2_medium")],
)
def test_priority_maps_to_its_queue(priority, queue):  # US-04
    assert queue_for_priority(priority) == queue


def test_queue_names_sort_in_priority_order():  # US-04 AC1, AC2
    names = [q.name for q in celery_app.conf.task_queues]
    assert names == ["p1_high", "p2_medium", "p3_low"]
    assert names == sorted(names)
    assert celery_app.conf.broker_transport_options["queue_order_strategy"] == "sorted"


def test_enqueue_sends_the_job_to_the_matching_queue(monkeypatch):
    fake = _FakeTask()
    monkeypatch.setattr(processing_tasks, "run_batch_processing", fake)
    processing_tasks.enqueue_batch_processing("BATCH-1", "high")
    assert fake.sent == [(["BATCH-1"], "p1_high")]


def test_start_processing_passes_the_batch_priority_to_the_queue():
    batch_id = _create("low")
    seen = []
    processing_service.start_processing(batch_id, USER, lambda b, p: seen.append((b, p)))
    assert seen == [(batch_id, "low")]


def test_started_at_is_set_by_the_worker_not_when_queued():
    batch_id = _create("high")
    processing_service.start_processing(batch_id, USER, lambda b, p: None)  # queued, no worker yet
    assert client.get(f"/batches/{batch_id}").json()["started_at"] is None

    processing_service.process_batch(batch_id, MockExtractionService(), MockOcrService())
    assert client.get(f"/batches/{batch_id}").json()["started_at"] is not None