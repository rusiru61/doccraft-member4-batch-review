import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.integrations.extraction_service import MockExtractionService
from app.integrations.ocr_service import MockOcrService
from app.main import app
from app.services import processing_service
from app.services.processing_service import QueueUnavailableError

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)
BASE = {"template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE"}


def _post(**overrides):
    body = {**BASE, "document_ids": ["DOC-001"], **overrides}
    return client.post("/api/v1/extraction-jobs", json=body)


def _job(job_id):
    return client.get(f"/api/v1/extraction-jobs/{job_id}").json()


def test_create_starts_processing_and_answers_202():
    response = _post(document_ids=["DOC-001", "DOC-003"])
    body = response.json()
    assert response.status_code == 202
    assert body["status"] == "queued"
    job = _job(body["job_id"])
    assert job["status"] == "review_required"  # the test run executes the worker in-process
    assert job["progress"]["completed"] == 2


def test_name_and_priority_are_optional():
    job = _job(_post().json()["job_id"])
    assert job["name"].startswith("Job ")
    assert job["priority"] == "medium"


def test_start_false_creates_a_job_without_starting_it():
    response = _post(start=False)
    assert response.status_code == 201
    job = _job(response.json()["job_id"])
    assert job["status"] == "queued"
    assert job["items"][0]["status"] == "pending"


def test_a_job_created_without_starting_can_be_started_later():
    job_id = _post(start=False).json()["job_id"]
    assert client.post(f"/api/v1/extraction-jobs/{job_id}/process").status_code == 202
    assert _job(job_id)["status"] == "review_required"
    assert client.post(f"/api/v1/extraction-jobs/{job_id}/process").status_code == 409


def test_job_records_template_mapping_and_version():
    job = _job(_post().json()["job_id"])
    assert job["template_id"] == "TEMPLATE-INVOICE"
    assert job["mapping_id"] == "MAPPING-INVOICE"
    assert job["mapping_version"] == 2
    stored = get_db().extraction_results.find_one({})
    assert stored["template_id"] == "TEMPLATE-INVOICE"
    assert stored["mapping_id"] == "MAPPING-INVOICE"


def test_missing_template_is_a_validation_error():
    body = {"mapping_id": "MAPPING-INVOICE", "document_ids": ["DOC-001"]}
    response = client.post("/api/v1/extraction-jobs", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body.template_id"


@pytest.mark.parametrize(
    "overrides, status, code",
    [
        ({"template_id": "TEMPLATE-NOPE"}, 422, "TEMPLATE_NOT_FOUND"),
        ({"template_id": "TEMPLATE-RETIRED"}, 409, "TEMPLATE_INACTIVE"),
        ({"mapping_id": "MAPPING-NOPE"}, 422, "MAPPING_NOT_FOUND"),
        ({"mapping_id": "MAPPING-RECEIPT"}, 422, "MAPPING_TEMPLATE_MISMATCH"),
        ({"mapping_id": "MAPPING-DRAFT"}, 409, "MAPPING_INACTIVE"),
        ({"document_ids": ["DOC-999"]}, 422, "DOCUMENT_NOT_FOUND"),
    ],
)
def test_unusable_references_are_rejected_with_stable_codes(overrides, status, code):
    response = _post(**overrides)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert client.get("/api/v1/extraction-jobs").json()["total"] == 0  # nothing was created


def test_queue_outage_on_create_keeps_the_job_startable(monkeypatch):
    def broken_queue(job_id, priority):
        raise QueueUnavailableError(job_id)

    with monkeypatch.context() as patch:
        patch.setattr("app.api.jobs.enqueue_job_processing", broken_queue)
        response = _post()

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "QUEUE_UNAVAILABLE"
    listed = client.get("/api/v1/extraction-jobs").json()
    assert listed["total"] == 1 and listed["items"][0]["status"] == "queued"
    job_id = listed["items"][0]["job_id"]
    assert job_id in response.json()["error"]["message"]

    assert client.post(f"/api/v1/extraction-jobs/{job_id}/process").status_code == 202
    assert _job(job_id)["status"] == "review_required"


def test_job_results_endpoint_returns_extracted_values():
    job_id = _post(document_ids=["DOC-001", "DOC-008"]).json()["job_id"]
    response = client.get(f"/api/v1/extraction-jobs/{job_id}/results")
    assert response.status_code == 200
    by_doc = {r["document_id"]: r for r in response.json()}
    assert by_doc["DOC-001"]["field_values"]["invoice_number"]["value"] == "INV-001"
    assert by_doc["DOC-008"]["status"] == "failed"
    assert by_doc["DOC-008"]["field_values"] is None
    assert client.get("/api/v1/extraction-jobs/JOB-NOPE/results").status_code == 404


def test_the_worker_ignores_an_unknown_job():
    processing_service.process_job("0" * 24, MockExtractionService(), MockOcrService())


def test_the_extraction_engine_receives_the_mapping_id():
    seen = []

    class Spy:
        def extract(self, document_id, mapping_id=None):
            seen.append(mapping_id)
            return MockExtractionService().extract(document_id)

    job_id = _post(start=False).json()["job_id"]
    processing_service.process_job(job_id, Spy(), MockOcrService())
    assert seen == ["MAPPING-INVOICE"]