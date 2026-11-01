from typing import Protocol

from app.schemas.data_structure import FieldDefinition


class DataStructureProvider(Protocol):
    def get_field_definitions(self, data_structure_id: str | None = None) -> list[FieldDefinition]: ...


_INVOICE_FIELDS = [
    FieldDefinition(field_id="invoice_number", name="Invoice Number", type="text",
                    required=True, description="Unique invoice identifier", order=1),
    FieldDefinition(field_id="total_amount", name="Total Amount", type="currency",
                    required=True, description="Final invoice total", order=2),
    FieldDefinition(field_id="supplier_name", name="Supplier Name", type="text",
                    required=True, description="Name of the supplier", order=3),
]


class MockDataStructureProvider:
    """Fake stand-in for Member 2. Always returns the same invoice data structure."""

    def get_field_definitions(self, data_structure_id: str | None = None) -> list[FieldDefinition]:
        return [f.model_copy() for f in _INVOICE_FIELDS]


def get_data_structure_provider() -> DataStructureProvider:
    """THE swap point for Member 2's data structures."""
    return MockDataStructureProvider()