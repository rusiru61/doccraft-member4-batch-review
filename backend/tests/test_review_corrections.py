import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app

pytestmark = pytest.mark.usefixtures("clean_test_db")
client = TestClient(app)


def _first_task():
    body = {"name": "T", "priority": "high", "document_ids": ["DOC-003"]}
    batch_id = client.post("/batches", json=body).json()["batch_id"]
    client.post(f"/batches/{batch_id}/process")
    return client.get("/review-tasks").json()[0]


def _fix_supplier(task_id, value="ABC Traders"):
    body = {"corrections": [{"name": "supplier_name", "value": value}]}
    return client.patch(f"/review-tasks/{task_id}/fields", json=body)


def _field(detail, name):
    return next(f for f in detail["fields"] if f["name"] == name)


def test_detail_shows_flagged_missing_field():
    task = _first_task()
    detail = client.get(f"/review-tasks/{task['task_id']}").json()
    supplier = _field(detail, "supplier_name")
    assert supplier["flagged"] and not supplier["found"]
    assert supplier["current_value"] is None
    assert detail["validation_errors"] == ["Missing supplier name"]


def test_correction_is_saved():  # US-08 AC1
    task = _first_task()
    response = _fix_supplier(task["task_id"])
    assert response.status_code == 200
    supplier = _field(response.json(), "supplier_name")
    assert supplier["current_value"] == "ABC Traders"
    assert supplier["original_value"] is None
    assert supplier["corrected"] is True


def test_reopened_task_shows_corrected_values():  # US-08 AC2
    task = _first_task()
    _fix_supplier(task["task_id"])
    detail = client.get(f"/review-tasks/{task['task_id']}").json()
    assert _field(detail, "supplier_name")["current_value"] == "ABC Traders"


def test_original_extraction_is_never_overwritten():
    task = _first_task()
    _fix_supplier(task["task_id"])
    item = get_db().job_items.find_one({"item_id": task["item_id"]})
    original = next(f for f in item["extraction"]["fields"] if f["name"] == "supplier_name")
    assert original["value"] is None


def test_correction_records_who_and_when():
    task = _first_task()
    _fix_supplier(task["task_id"])
    saved = get_db().review_tasks.find_one({"task_id": task["task_id"]})
    assert saved["corrections"]["supplier_name"]["corrected_by"] == "user_001"
    assert saved["corrections"]["supplier_name"]["corrected_at"] is not None


def test_unknown_field_is_rejected():
    task = _first_task()
    body = {"corrections": [{"name": "not_a_field", "value": "x"}]}
    assert client.patch(f"/review-tasks/{task['task_id']}/fields", json=body).status_code == 422


def test_blank_value_is_rejected():
    task = _first_task()
    assert _fix_supplier(task["task_id"], value="   ").status_code == 422


def test_completed_task_cannot_be_edited():
    task = _first_task()
    get_db().review_tasks.update_one(
        {"task_id": task["task_id"]}, {"$set": {"status": "approved"}}
    )
    assert _fix_supplier(task["task_id"]).status_code == 409


def test_unknown_task_returns_404():
    assert client.get("/review-tasks/REV-NOPE").status_code == 404
    assert _fix_supplier("REV-NOPE").status_code == 404