import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from bson import ObjectId

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _first_task():
    body = {"name": "T", "priority": "high", "document_ids": ["DOC-003"]}
    job_id = client.post("/api/v1/jobs", json=body).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/process")
    return client.get("/api/v1/review-tasks").json()[0]


def _fix_supplier(result_id, value="ABC Traders"):
    body = {"corrections": [{"field_id": "supplier_name", "value": value}]}
    return client.patch(f"/api/v1/review-tasks/{result_id}/fields", json=body)


def _field(detail, field_id):
    return next(f for f in detail["fields"] if f["field_id"] == field_id)


def test_detail_shows_fields_in_order_with_the_flagged_one_marked():
    task = _first_task()
    detail = client.get(f"/api/v1/review-tasks/{task['result_id']}").json()
    assert [f["field_id"] for f in detail["fields"]] == [
        "invoice_number", "total_amount", "supplier_name",
    ]
    supplier = _field(detail, "supplier_name")
    assert supplier["name"] == "Supplier Name"
    assert supplier["flagged"] and supplier["status"] == "missing"
    assert supplier["current_value"] is None
    assert not _field(detail, "invoice_number")["flagged"]
    assert detail["validation_errors"] == ["Missing supplier name"]


def test_correction_is_saved():  # US-08 AC1
    task = _first_task()
    response = _fix_supplier(task["result_id"])
    assert response.status_code == 200
    supplier = _field(response.json(), "supplier_name")
    assert supplier["current_value"] == "ABC Traders"
    assert supplier["original_value"] is None
    assert supplier["status"] == "corrected"


def test_reopened_task_shows_corrected_values():  # US-08 AC2
    task = _first_task()
    _fix_supplier(task["result_id"])
    detail = client.get(f"/api/v1/review-tasks/{task['result_id']}").json()
    assert _field(detail, "supplier_name")["current_value"] == "ABC Traders"


def test_original_extraction_is_never_overwritten():
    task = _first_task()
    _fix_supplier(task["result_id"])
    stored = get_db().extraction_results.find_one({"_id": ObjectId(task["result_id"])})
    original = stored["field_values"]["supplier_name"]
    assert original["value"] is None and original["status"] == "missing"


def test_correction_records_who_and_when():
    task = _first_task()
    _fix_supplier(task["result_id"])
    saved = get_db().extraction_results.find_one({"_id": ObjectId(task["result_id"])})
    assert saved["corrections"]["supplier_name"]["corrected_by"] == "user_001"
    assert saved["corrections"]["supplier_name"]["corrected_at"] is not None


def test_unknown_field_is_rejected():
    task = _first_task()
    body = {"corrections": [{"field_id": "not_a_field", "value": "x"}]}
    response = client.patch(f"/api/v1/review-tasks/{task['result_id']}/fields", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNKNOWN_FIELD"


def test_blank_value_is_rejected():
    task = _first_task()
    assert _fix_supplier(task["result_id"], value="   ").status_code == 422


def test_approved_task_cannot_be_edited():
    task = _first_task()
    get_db().extraction_results.update_one(
        {"_id": ObjectId(task["result_id"])}, {"$set": {"review_status": "approved"}}
    )
    assert _fix_supplier(task["result_id"]).status_code == 409


def test_unknown_task_returns_404():
    assert client.get("/api/v1/review-tasks/REV-NOPE").status_code == 404
    assert _fix_supplier("REV-NOPE").status_code == 404