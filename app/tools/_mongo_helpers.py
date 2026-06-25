from bson import ObjectId
from typing import Any


def to_object_id(value: str):
    try:
        return ObjectId(value)
    except Exception:
        return value


def json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value
