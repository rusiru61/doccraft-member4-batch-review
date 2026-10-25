from fastapi.testclient import TestClient

from app.main import app
from app.services.processing_service import order_items

client = TestClient(app)
TEN_DOCS = [f"DOC-{n:03d}" for n in range(1, 11)]


def _create(ids):
    body = {"name": "T", "priority": "high", "document_ids": ids}
    return client.post("/batches", json=body).json()["batch_id"]


def test_order_items_is_shortest_first():  # US-12 AC (no database needed)
    items = [
        {"document_id": "A", "page_count": 20, "text_length": 100},
        {"document_id": "B", "page_count": 2, "text_length": 50},
        {"document_id": "C", "page_count": 8, "text_length": 10},
    ]
    assert [i["document_id"] for i in order_items(items)] == ["B", "C", "A"]


def test_order_items_breaks_page_ties_by_text_length():
    items = [
        {"document_id": "A", "page_count": 2, "text_length": 900},
        {"document_id": "B", "page_count": 2, "text_length": 100},
    ]
    assert [i["document_id"] for i in order_items(items)] == ["B", "A"]


def test_one_failure_does_not_stop_the_batch(clean_test_db):  # US-03 AC1, AC2
    batch_id = _create(TEN_DOCS)
    assert client.post(f"/batches/{batch_id}/process").status_code == 202

    detail = client.get(f"/batches/{batch_id}").json()
    progress = detail["progress"]
    assert detail["status"] == "completed"
    assert (progress["completed"], progress["failed"]) == (9, 1)
    assert progress["percent_complete"] == 100.0

    failed = [i for i in detail["items"] if i["status"] == "failed"]
    assert failed[0]["document_id"] == "DOC-008"
    assert failed[0]["error_message"]


def test_processing_follows_shortest_first_order(clean_test_db):  # US-12
    batch_id = _create(["DOC-002", "DOC-001", "DOC-004"])  # 20, 2, 8 pages
    client.post(f"/batches/{batch_id}/process")

    items = client.get(f"/batches/{batch_id}").json()["items"]
    in_order = sorted(items, key=lambda i: i["processing_order"])
    assert [i["document_id"] for i in in_order] == ["DOC-001", "DOC-004", "DOC-002"]


def test_cannot_process_the_same_batch_twice(clean_test_db):
    batch_id = _create(["DOC-001"])
    assert client.post(f"/batches/{batch_id}/process").status_code == 202
    assert client.post(f"/batches/{batch_id}/process").status_code == 409


def test_process_unknown_batch_returns_404(clean_test_db):
    assert client.post("/batches/BATCH-DOESNOTEXIST/process").status_code == 404