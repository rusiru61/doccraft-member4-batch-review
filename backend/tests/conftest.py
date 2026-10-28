import pytest

from app.core.config import settings
from app.core.database import ensure_indexes, get_client

TEST_DB = "doccraft_member4_test"


@pytest.fixture
def clean_test_db(monkeypatch):
    monkeypatch.setattr(settings, "mongodb_db_name", TEST_DB)
    monkeypatch.setattr(settings, "mock_processing_delay_seconds", 0)
    get_client().drop_database(TEST_DB)
    ensure_indexes()
    yield