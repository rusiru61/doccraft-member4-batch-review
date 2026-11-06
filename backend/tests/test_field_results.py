import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.integrations.data_structure_provider import MockDataStructureProvider
from app.integrations.extraction_service import MockExtractionService
from app.main import app
from app.schemas.data_structure import FieldDefinition
from app.schemas.extraction import FieldResult
from app.services import extraction_rules, processing_service
from bson import ObjectId

client = TestClient(app)

DEFS = [
    FieldDefinition(field_id="a", name="A", type="text", required=True, order=1),
    FieldDefinition(field_id="b", name="B", type="text", required=False, order=2),
]


@pytest.fixture(autouse=True)
def no_delay(monkeypatch):
    monkeypatch.setattr(settings, "mock_processing_delay_seconds", 0)


class _ConfidentButIncomplete:
    """Engine stub: top confidence, but a required field is missing."""

    def extract(self, document_id, mapping_id=None):
        result = MockExtractionService().extract("DOC-001")
        result.field_values["supplier_name"] = FieldResult(value=None, status="missing")
        result.ai_confidence = 1.0
        return result


class _PerfectOcr:
    def get_ocr_confidence(self, document_id, is_scanned):
        return 1.0


def test_mock_returns_team_shaped_field_results():
    result = MockExtractionService().extract("DOC-001")
    assert set(result.field_values) == {"invoice_number", "total_amount", "supplier_name"}
    invoice = result.field_values["invoice_number"]
    assert invoice.status == "extracted"
    assert invoice.source_text == "Invoice No: INV-001"


def test_mock_can_return_missing_and_invalid_fields():
    missing = MockExtractionService().extract("DOC-003").field_values["supplier_name"]
    invalid = MockExtractionService().extract("DOC-006").field_values["supplier_name"]
    assert (missing.status, missing.value) == ("missing", None)
    assert (invalid.status, invalid.value) == ("invalid", "???")


def test_flagged_fields_are_the_missing_or_invalid_ones():
    values = {"a": {"status": "extracted"}, "b": {"status": "missing"}, "c": {"status": "invalid"}}
    assert extraction_rules.find_flagged_fields(values) == ["b", "c"]


def test_required_problems_ignore_optional_fields():
    values = {"a": {"status": "missing"}, "b": {"status": "missing"}}
    assert extraction_rules.find_required_problems(values, DEFS) == ["a"]


def test_absent_required_field_counts_as_missing():
    assert extraction_rules.find_required_problems({}, DEFS) == ["a"]


def test_final_fields_prefer_corrections_and_ignore_unexpected_keys():
    values = {
        "a": {"value": None, "status": "missing", "source_text": None},
        "zzz": {"value": "x", "status": "extracted", "source_text": None},
    }
    final = extraction_rules.build_final_fields(values, {"a": {"value": "fixed"}}, DEFS)
    assert final == [
        {"field_id": "a", "name": "A", "value": "fixed", "status": "corrected"},
        {"field_id": "b", "name": "B", "value": None, "status": "missing"},
    ]


@pytest.mark.usefixtures("clean_test_db")
def test_field_definitions_are_snapshotted_on_each_item():
    body = {"name": "T", "priority": "high", "template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE", "start": False, "document_ids": ["DOC-001"]}
    job_id = client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    item = get_db().extraction_results.find_one({"job_id": ObjectId(job_id)})
    assert [d["field_id"] for d in item["field_definitions"]] == [
        d.field_id for d in MockDataStructureProvider().get_field_definitions()
    ]


@pytest.mark.usefixtures("clean_test_db")
def test_invalid_required_field_blocks_finalizing_until_corrected():
    body = {"name": "T", "priority": "high", "template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE", "start": False, "document_ids": ["DOC-006"]}
    job_id = client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]
    client.post(f"/api/v1/extraction-jobs/{job_id}/process")
    task = client.get("/api/v1/extraction-results").json()[0]

    detail = client.get(f"/api/v1/extraction-results/{task['result_id']}").json()
    supplier = next(f for f in detail["fields"] if f["field_id"] == "supplier_name")
    assert (supplier["status"], supplier["current_value"], supplier["flagged"]) == ("invalid", "???", True)

    assert client.post(f"/api/v1/extraction-results/{task['result_id']}/approve").status_code == 422
    fix = {"corrections": [{"field_id": "supplier_name", "value": "ABC Traders"}]}
    client.patch(f"/api/v1/extraction-results/{task['result_id']}", json=fix)
    assert client.post(f"/api/v1/extraction-results/{task['result_id']}/approve").status_code == 200


@pytest.mark.usefixtures("clean_test_db")
def test_perfect_scores_still_go_to_review_when_a_required_field_is_missing():
    body = {"name": "T", "priority": "high", "template_id": "TEMPLATE-INVOICE", "mapping_id": "MAPPING-INVOICE", "start": False, "document_ids": ["DOC-001"]}
    job_id = client.post("/api/v1/extraction-jobs", json=body).json()["job_id"]
    processing_service.process_job(job_id, _ConfidentButIncomplete(), _PerfectOcr())

    tasks = client.get("/api/v1/extraction-results").json()
    assert len(tasks) == 1
    assert tasks[0]["reliability_score"] == 0.8  # exactly the threshold, so the score alone passes
    assert tasks[0]["review_reasons"] == ["required_field_problem"]