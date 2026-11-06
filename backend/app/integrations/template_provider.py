from typing import Protocol

from app.schemas.configuration import TemplateInfo


class TemplateProvider(Protocol):
    def get_template(self, template_id: str) -> TemplateInfo | None: ...


_TEMPLATES = [
    TemplateInfo(template_id="TEMPLATE-INVOICE", name="Vendor A Invoice", is_active=True),
    TemplateInfo(template_id="TEMPLATE-RECEIPT", name="Shop Receipt", is_active=True),
    TemplateInfo(template_id="TEMPLATE-RETIRED", name="Old Layout", is_active=False),
]


class MockTemplateProvider:
    """Fake stand-in for Member 2's templates."""

    def __init__(self) -> None:
        self._templates = {t.template_id: t for t in _TEMPLATES}

    def get_template(self, template_id: str) -> TemplateInfo | None:
        return self._templates.get(template_id)


def get_template_provider() -> TemplateProvider:
    """THE swap point for Member 2's templates."""
    return MockTemplateProvider()