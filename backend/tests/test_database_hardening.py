import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.core.database import ensure_indexes, get_db
from app.main import app
from app.repositories import batch_repository

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _create(ids=("DOC-001",)):
    body = {"name": "T", "priority": "high", "document_ids": list(ids)}
    return client.post("/batches", json=body).json()["batch_id"]


def test_ensure_indexes_is_idempotent():
    ensure_indexes()
    ensure_indexes()  # must not raise


def test_expected_indexes_exist():
    db = get_db()
    assert "batch_id_1" in db.batches.index_information()
    assert {"item_id_1", "batch_id_1"} <= set(db.job_items.index_information())
    assert "task_id_1" in db.review_tasks.index_information()
    assert "status_1_reliability_score_1_created_at_1" in db.review_tasks.index_information()
    assert "audit_id_1" in db.audit_log.index_information()


@pytest.mark.parametrize(
    "collection, key",
    [
        ("batches", "batch_id"),
        ("job_items", "item_id"),
        ("review_tasks", "task_id"),
        ("audit_log", "audit_id"),
    ],
)
def test_unique_ids_are_enforced_by_the_database(collection, key):
    target = getattr(get_db(), collection)
    target.insert_one({key: "X-1"})
    with pytest.raises(DuplicateKeyError):
        target.insert_one({key: "X-1"})


def test_list_batches_does_not_query_once_per_batch(monkeypatch):
    for _ in range(3):
        _create()

    def forbidden(*args, **kwargs):
        raise AssertionError("count_by_status must not be called once per batch")

    monkeypatch.setattr(batch_repository, "count_by_status", forbidden)
    response = client.get("/batches")
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_list_progress_matches_detail_progress():
    batch_id = _create([f"DOC-{n:03d}" for n in range(1, 11)])
    client.post(f"/batches/{batch_id}/process")
    listed = client.get("/batches").json()[0]
    detail = client.get(f"/batches/{batch_id}").json()
    assert listed["progress"] == detail["progress"]