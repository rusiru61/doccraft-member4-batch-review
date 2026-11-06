import pytest
from fastapi.testclient import TestClient

from app.integrations.output_service import get_output_service
from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
TEN_DOCS = [f"DOC-{n:03d}" for n in range(1, 11)]


class _FakeOutput:
    def __init__(self, fail: bool = False):
        self.calls = []
        self.fail = fail

    def deliver(self, job_id):
        self.calls.append(job_id)
        if self.fail:
            raise RuntimeError("delivery service is down")


@pytest.fixture
def output():
    fake = _FakeOutput()
    app.dependency_overrides[get_output_service] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_output_service, None)


@pytest.fixture
def failing_output():
    fake = _FakeOutput(fail=True)
    app.dependency_overrides[get_output_service] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_output_service, None)


def _create(ids):
    body = {"name": "T", "priority": "high", "template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE", "start": False, "document_ids": list(ids)}
    return client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]


def _process(ids):
    job_id = _create(ids)
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    return job_id


def _job(job_id):
    return client.get(f"/api/v1/extraction-jobs/{job_id}").json()


def _finalize(job_id):
    return client.post(f"/api/v1/extraction-jobs/{job_id}/finalize")


def _review_everything():
    fix = {"corrections": [{"field_id": "supplier_name", "value": "ABC Traders"}]}
    for result in client.get("/api/v1/extraction-results").json():
        client.patch(f"/api/v1/extraction-results/{result['result_id']}", json=fix)
        client.post(f"/api/v1/extraction-results/{result['result_id']}/approve")


def test_new_job_is_queued():
    assert _job(_create(["DOC-001"]))["status"] == "queued"


def test_job_with_results_waiting_for_review_needs_review():
    assert _job(_process(TEN_DOCS))["status"] == "review_required"


def test_clean_job_still_waits_for_finalize():
    job_id = _process(["DOC-001", "DOC-002"])
    assert _job(job_id)["status"] == "review_required"
    assert client.get("/api/v1/extraction-results").json() == []


def test_job_where_every_document_fails_is_failed():
    job_id = _process(["DOC-008"])
    assert _job(job_id)["status"] == "failed"
    response = _finalize(job_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_NOT_FINALIZABLE"


def test_cannot_finalize_while_reviews_are_pending(output):
    job_id = _process(TEN_DOCS)
    response = _finalize(job_id)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVIEWS_PENDING"
    assert "3" in response.json()["error"]["message"]
    assert output.calls == []
    assert _job(job_id)["status"] == "review_required"


def test_finalizing_after_review_marks_failed_documents_as_partially_failed(output):
    job_id = _process(TEN_DOCS)
    _review_everything()
    response = _finalize(job_id)
    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "partially_failed"
    assert body["completed_at"] is not None
    assert body["finalized_by"] == "user_001"
    assert (body["progress"]["completed"], body["progress"]["failed"]) == (9, 1)


def test_finalizing_a_clean_job_completes_it(output):
    job_id = _process(["DOC-001", "DOC-002"])
    response = _finalize(job_id)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert output.calls == [job_id]


def test_cannot_finalize_twice_and_delivery_is_requested_once(output):
    job_id = _process(["DOC-001"])
    assert _finalize(job_id).status_code == 200
    second = _finalize(job_id)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "JOB_NOT_FINALIZABLE"
    assert output.calls == [job_id]


def test_cannot_finalize_a_queued_job(output):
    job_id = _create(["DOC-001"])
    assert _finalize(job_id).status_code == 409
    assert output.calls == []


def test_finalize_unknown_job_returns_404():
    response = _finalize("JOB-NOPE")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_a_delivery_failure_does_not_undo_finalizing(failing_output):
    job_id = _process(["DOC-001"])
    response = _finalize(job_id)
    assert response.status_code == 200
    assert _job(job_id)["status"] == "completed"
    assert failing_output.calls == [job_id]


def test_finalizing_is_audited_once(output):
    job_id = _process(["DOC-001"])
    _finalize(job_id)
    _finalize(job_id)  # rejected, so it must not be audited
    page = client.get("/api/v1/audit-log", params={"action": "job.finalized"}).json()
    assert page["total"] == 1
    assert page["items"][0]["entity_id"] == job_id


def test_job_list_is_the_job_history():
    job_id = _process(["DOC-001", "DOC-002"])
    page = client.get("/api/v1/extraction-jobs").json()
    assert {"items", "total", "page", "page_size"} <= set(page)
    entry = page["items"][0]
    assert entry["job_id"] == job_id
    assert entry["percent_complete"] == 100.0
    assert client.get("/api/v1/job-history").status_code == 404