from app.schemas.routing import LanguageRouting

# language code -> (pipeline name, OCR language pack, needs human review?)
_ROUTES = {
    "en": ("English Pipeline", "eng", False),
    "si": ("Sinhala Pipeline", "sin", False),
    "ta": ("Tamil Pipeline", "tam", False),
}
_DEFAULT_ROUTE = ("Default Pipeline", "eng+sin+tam", True)


def route_language(language_code: str) -> LanguageRouting:
    """Decide which pipeline a document goes through. Unknown languages never get guessed."""
    pipeline, ocr_language, requires_review = _ROUTES.get(language_code, _DEFAULT_ROUTE)
    return LanguageRouting(
        language=language_code,
        pipeline=pipeline,
        ocr_language=ocr_language,
        requires_review=requires_review,
    )