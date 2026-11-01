from app.schemas.data_structure import FieldDefinition

PROBLEM_STATUSES = ("missing", "invalid")
_NO_VALUE = {"value": None, "status": "missing", "source_text": None}


def find_flagged_fields(field_values: dict) -> list[str]:
    """Every field that is missing or invalid, required or not."""
    return [fid for fid, fv in field_values.items() if fv.get("status") in PROBLEM_STATUSES]


def find_required_problems(field_values: dict, definitions: list[FieldDefinition]) -> list[str]:
    """Required fields that are missing or invalid. A field absent from the result counts as missing."""
    return [
        d.field_id
        for d in sorted(definitions, key=lambda d: d.order)
        if d.required and (field_values.get(d.field_id) or _NO_VALUE)["status"] in PROBLEM_STATUSES
    ]


def build_final_fields(
    field_values: dict, corrections: dict, definitions: list[FieldDefinition]
) -> list[dict]:
    """The correction wins when there is one. Keys the engine returned that are not
    in the data structure are ignored."""
    final = []
    for d in sorted(definitions, key=lambda d: d.order):
        original = field_values.get(d.field_id) or _NO_VALUE
        if d.field_id in corrections:
            value, status = corrections[d.field_id]["value"], "corrected"
        else:
            value, status = original["value"], original["status"]
        final.append({"field_id": d.field_id, "name": d.name, "value": value, "status": status})
    return final