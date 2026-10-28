import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.services.routing_service import route_language

client = TestClient(app)


def _create(ids):
    body = {"name": "T", "priority": "high", "document_ids": ids}
    return client.post("/batches", json=body).json()["batch_id"]


def _process(ids):
    batch_id = _create(ids)
    client.post(f"/batches/{batch_id}/process")
    return batch_id


def _items(batch_id):
    return {i["document_id"]: i for i in client.get(f"/batches/{batch_id}").json()["items"]}


def _make_unknown(batch_id):
    get_db().job_items.update_many(
        {"batch_id": batch_id}, {"$set": {"detected_language": "unknown"}}
    )


@pytest.mark.parametrize(
    "code, pipeline, ocr_language",
    [("en", "English Pipeline", "eng"), ("si", "Sinhala Pipeline", "sin"), ("ta", "Tamil Pipeline", "tam")],
)
def test_known_languages_route_to_their_pipeline(code, pipeline, ocr_language):  # US-10 AC1-3
    routing = route_language(code)
    assert routing.pipeline == pipeline
    assert routing.ocr_language == ocr_language
    assert routing.requires_review is False


def test_unknown_language_goes_to_default_pipeline_and_review():  # US-10 AC4
    routing = route_language("unknown")
    assert routing.pipeline == "Default Pipeline"
    assert routing.requires_review is True


def test_unexpected_code_is_treated_like_unknown():
    assert route_language("fr").pipeline == "Default Pipeline"


def test_items_record_their_routing_decision(clean_test_db):
    items = _items(_process(["DOC-001", "DOC-005", "DOC-006"]))
    assert items["DOC-001"]["language_routing"]["pipeline"] == "English Pipeline"
    assert items["DOC-005"]["language_routing"]["pipeline"] == "Sinhala Pipeline"
    assert items["DOC-006"]["language_routing"]["pipeline"] == "Tamil Pipeline"


def test_unknown_language_forces_review_even_with_high_score(clean_test_db):
    batch_id = _create(["DOC-001"])  # DOC-001 normally scores about 0.96 and passes
    _make_unknown(batch_id)
    client.post(f"/batches/{batch_id}/process")

    tasks = client.get("/review-tasks").json()
    assert len(tasks) == 1
    assert tasks[0]["review_reasons"] == ["unknown_language"]
    assert _items(batch_id)["DOC-001"]["review_status"] == "pending_review"
    assert client.get("/finalized-results").json() == []


def test_failed_document_still_has_routing_and_no_task(clean_test_db):
    batch_id = _process(["DOC-008"])
    item = _items(batch_id)["DOC-008"]
    assert item["status"] == "failed"
    assert item["language_routing"]["pipeline"] == "Default Pipeline"
    assert client.get("/review-tasks").json() == []


def test_low_score_task_records_low_reliability_reason(clean_test_db):
    _process(["DOC-003"])
    assert client.get("/review-tasks").json()[0]["review_reasons"] == ["low_reliability"]


def test_task_can_have_both_reasons(clean_test_db):
    batch_id = _create(["DOC-003"])  # low score
    _make_unknown(batch_id)
    client.post(f"/batches/{batch_id}/process")
    reasons = client.get("/review-tasks").json()[0]["review_reasons"]
    assert reasons == ["low_reliability", "unknown_language"]