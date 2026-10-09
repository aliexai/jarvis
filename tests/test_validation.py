"""JSON schema validation tests (shared by tools and structured output)."""

from __future__ import annotations

from nova.validation import is_valid, validate

SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "maxLength": 5},
        "count": {"type": "integer", "minimum": 1, "maximum": 10},
        "mode": {"type": "string", "enum": ["a", "b"]},
    },
    "required": ["text"],
    "additionalProperties": False,
}


def test_valid_object_passes():
    assert validate({"text": "ok"}, SCHEMA) == []
    assert is_valid({"text": "ok", "count": 3, "mode": "a"}, SCHEMA)


def test_missing_required_field():
    errors = validate({}, SCHEMA)
    assert any("required" in error for error in errors)


def test_wrong_type_is_reported():
    errors = validate({"text": 5}, SCHEMA)
    assert any("expected string" in error for error in errors)


def test_extra_properties_are_rejected():
    errors = validate({"text": "ok", "sneaky": "value"}, SCHEMA)
    assert any("not allowed" in error for error in errors)


def test_max_length_enforced():
    assert validate({"text": "abcdef"}, SCHEMA)


def test_numeric_bounds_enforced():
    assert validate({"text": "ok", "count": 0}, SCHEMA)
    assert validate({"text": "ok", "count": 99}, SCHEMA)
    assert validate({"text": "ok", "count": 5}, SCHEMA) == []


def test_enum_enforced():
    assert validate({"text": "ok", "mode": "z"}, SCHEMA)


def test_booleans_are_not_integers():
    errors = validate({"text": "ok", "count": True}, SCHEMA)
    assert any("expected integer" in error for error in errors)


def test_nested_arrays_and_objects():
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "maxItems": 2,
                "items": {
                    "type": "object",
                    "properties": {"n": {"type": "integer"}},
                    "required": ["n"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    }
    assert validate({"items": [{"n": 1}, {"n": 2}]}, schema) == []
    assert validate({"items": [{"n": 1}, {"n": 2}, {"n": 3}]}, schema)
    assert validate({"items": [{"n": "x"}]}, schema)


def test_missing_schema_is_permissive():
    assert validate({"anything": 1}, None) == []
    assert validate({"anything": 1}, {}) == []
