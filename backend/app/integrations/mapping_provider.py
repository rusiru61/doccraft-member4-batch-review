from typing import Protocol

from app.schemas.configuration import MappingInfo


class MappingProvider(Protocol):
    def get_mapping(self, mapping_id: str) -> MappingInfo | None: ...


_MAPPINGS = [
    MappingInfo(mapping_id="MAPPING-INVOICE", template_id="TEMPLATE-INVOICE",
                data_structure_id="DS-INVOICE", version=2, is_active=True),
    MappingInfo(mapping_id="MAPPING-RECEIPT", template_id="TEMPLATE-RECEIPT",
                data_structure_id="DS-INVOICE", version=1, is_active=True),
    MappingInfo(mapping_id="MAPPING-DRAFT", template_id="TEMPLATE-INVOICE",
                data_structure_id="DS-INVOICE", version=1, is_active=False),
]


class MockMappingProvider:
    """Fake stand-in for Member 3's mappings."""

    def __init__(self) -> None:
        self._mappings = {m.mapping_id: m for m in _MAPPINGS}

    def get_mapping(self, mapping_id: str) -> MappingInfo | None:
        return self._mappings.get(mapping_id)


def get_mapping_provider() -> MappingProvider:
    """THE swap point for Member 3's mappings."""
    return MockMappingProvider()