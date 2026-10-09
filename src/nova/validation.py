"""Minimal JSON Schema validation for the subset NOVA relies on.

Used for two things: validating model-produced tool arguments before they reach
a handler, and validating structured (JSON-mode) model output. Deliberately
dependency-free and strict: unknown properties are rejected when the schema sets
``additionalProperties: false``.
"""

from __future__ import annotations

import re
from typing import Any

_TYPE_CHECKS: dict[str, Any] = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(instance: Any, schema: dict[str, Any] | None) -> list[str]:
    """Return a list of human-readable validation errors (empty means valid)."""
    errors: list[str] = []
    _validate(instance, schema or {}, "$", errors)
    return errors


def is_valid(instance: Any, schema: dict[str, Any] | None) -> bool:
    return not validate(instance, schema)


def _validate(instance: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    if not isinstance(schema, dict) or not schema:
        return

    expected = schema.get("type")
    if expected is not None:
        options = expected if isinstance(expected, list) else [expected]
        if not any(_TYPE_CHECKS.get(str(option), lambda _v: True)(instance) for option in options):
            errors.append(f"{path}: expected {expected}, got {_type_name(instance)}")
            return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value is not one of {schema['enum']}")

    if isinstance(instance, str):
        _check_string(instance, schema, path, errors)

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and instance < minimum:
            errors.append(f"{path}: must be >= {minimum}")
        if maximum is not None and instance > maximum:
            errors.append(f"{path}: must be <= {maximum}")

    if isinstance(instance, dict):
        _check_object(instance, schema, path, errors)

    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(instance):
                _validate(value, items, f"{path}[{index}]", errors)
        max_items = schema.get("maxItems")
        if max_items is not None and len(instance) > max_items:
            errors.append(f"{path}: must have at most {max_items} items")


def _check_string(instance: str, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    max_length = schema.get("maxLength")
    if max_length is not None and len(instance) > max_length:
        errors.append(f"{path}: must be at most {max_length} characters")
    min_length = schema.get("minLength")
    if min_length is not None and len(instance) < min_length:
        errors.append(f"{path}: must be at least {min_length} characters")
    pattern = schema.get("pattern")
    if pattern is not None and not re.search(pattern, instance):
        errors.append(f"{path}: does not match pattern {pattern!r}")


def _check_object(instance: dict, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    properties = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in instance:
            errors.append(f"{path}.{key}: is required")
    if schema.get("additionalProperties") is False:
        for key in instance:
            if key not in properties:
                errors.append(f"{path}.{key}: is not allowed")
    for key, subschema in properties.items():
        if key in instance and isinstance(subschema, dict):
            _validate(instance[key], subschema, f"{path}.{key}", errors)


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    return type(value).__name__
