from typing import Literal

from pydantic import BaseModel

FieldType = Literal["text", "number", "date", "boolean", "currency", "enum", "table"]


class FieldDefinition(BaseModel):
    field_id: str
    name: str
    type: FieldType
    required: bool
    description: str = ""
    order: int
    is_repeating_group: bool = False