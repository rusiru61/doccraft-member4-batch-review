import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)

FIVE_DOCS = ["DOC-001", "DOC-002", "DOC-003", "DOC-004", "DOC-005"]
TEN_DOCS = [f"DOC-{n:03d}" for n in range(1, 11)]


def _create(ids, name="Demo", priority="high"):
    return client.post(
        "/batches", json={"name": name, "priority": priority, "document_ids": ids}
    )


def test_create_batch_has_pending_status_and_five_items():  # US-01 AC1, AC2
    response = _create(FIVE_DOCS)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "pending"
    assert body["progress"]["total"] == 5
    detail = client.get(f"/batches/{body['batch_id']}").json()
    assert len(detail["items"]) == 5


def test_duplicate_document_ids_create_one_item_each():
    body = _create(["DOC-001", "DOC-001", "DOC-002"]).json()
    assert body["progress"]["total"] == 2


def test_unknown_document_is_rejected():
    assert _create(["DOC-001", "DOC-999"]).status_code == 422


def test_empty_document_list_is_rejected():
    assert _create([]).status_code == 422


def test_unknown_batch_returns_404():
    assert client.get("/batches/BATCH-DOESNOTEXIST").status_code == 404


def test_progress_percentage():  # US-02 AC1, AC2
    batch_id = _create(TEN_DOCS).json()["batch_id"]
    items = get_db().job_items
    first_four = [i["item_id"] for i in items.find({"batch_id": batch_id}).limit(4)]
    items.update_many({"item_id": {"$in": first_four}}, {"$set": {"status": "completed"}})
    assert client.get(f"/batches/{batch_id}").json()["progress"]["percent_complete"] == 40.0

    items.update_many({"batch_id": batch_id}, {"$set": {"status": "completed"}})
    assert client.get(f"/batches/{batch_id}").json()["progress"]["percent_complete"] == 100.0