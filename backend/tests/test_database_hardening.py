import pytest
from fastapi.testclient import TestClient
from pymongo.errors import DuplicateKeyError

from app.core.database import ensure_indexes, get_db
from app.main import app
from app.repositories import job_repository
from bson import ObjectId

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _create(ids=("DOC-001",)):
    body = {"name": "T", "priority": "high", "document_ids": list(ids)}
    return client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]


def test_ensure_indexes_is_idempotent():
    ensure_indexes()
    ensure_indexes()  # must not raise


def test_expected_indexes_exist():
    db = get_db()
    results = db.extraction_results.index_information()
    assert "job_id_1_document_id_1" in results
    assert "review_status_1_reliability_score_1_created_at_1" in results
    assert "audit_id_1" in db.audit_logs.index_information()


def test_a_document_can_appear_only_once_per_job():
    results = get_db().extraction_results
    job_id = ObjectId()
    results.insert_one({"job_id": job_id, "document_id": "DOC-001"})
    with pytest.raises(DuplicateKeyError):
        results.insert_one({"job_id": job_id, "document_id": "DOC-001"})
    results.insert_one({"job_id": ObjectId(), "document_id": "DOC-001"})  # another job is fine


def test_audit_ids_are_unique():
    audit = get_db().audit_logs
    audit.insert_one({"audit_id": "AUD-1"})
    with pytest.raises(DuplicateKeyError):
        audit.insert_one({"audit_id": "AUD-1"})



def test_list_jobs_does_not_query_once_per_job(monkeypatch):
    for _ in range(3):
        _create()

    def forbidden(*args, **kwargs):
        raise AssertionError("count_by_status must not be called once per job")

    monkeypatch.setattr(job_repository, "count_by_status", forbidden)
    response = client.get("/api/v1/extraction-jobs")
    assert response.status_code == 200
    assert len(response.json()) == 3


def test_list_progress_matches_detail_progress():
    job_id = _create([f"DOC-{n:03d}" for n in range(1, 11)])
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    listed = client.get("/api/v1/extraction-jobs").json()[0]
    detail = client.get(f"/api/v1/extraction-jobs/{job_id}").json()
    assert listed["progress"] == detail["progress"]