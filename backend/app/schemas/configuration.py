from pydantic import BaseModel


class TemplateInfo(BaseModel):
    template_id: str
    name: str
    is_active: bool


class MappingInfo(BaseModel):
    mapping_id: str
    template_id: str
    data_structure_id: str
    version: int
    is_active: bool