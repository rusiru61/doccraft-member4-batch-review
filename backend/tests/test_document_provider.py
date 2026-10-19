from app.integrations.document_provider import get_document_provider


def test_provider_returns_ten_documents():
    assert len(get_document_provider().list_documents()) == 10


def test_get_document_by_id():
    doc = get_document_provider().get_document("DOC-005")
    assert doc is not None
    assert doc.detected_language == "si"


def test_unknown_id_returns_none():
    assert get_document_provider().get_document("DOC-999") is None


def test_all_languages_are_covered():
    languages = {d.detected_language for d in get_document_provider().list_documents()}
    assert languages == {"en", "si", "ta", "unknown"}