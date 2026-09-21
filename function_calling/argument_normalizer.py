"""FarmAgent coercion helpers, extended with validation and nested schemas."""

from __future__ import annotations

import math
import re
from typing import Any


_INT_PATTERN = re.compile(r"^[+-]?\d+$")
_FLOAT_PATTERN = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)$")


def _extract_string_from_schema_dict(value: dict[str, Any]) -> str | None:
    description = value.get("description")
    if isinstance(description, str):
        return description

    content = value.get("content")
    if isinstance(content, dict):
        content_description = content.get("description")
        if isinstance(content_description, str):
            return content_description

    return None


def _coerce_to_integer(value: Any, *, argument_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(
            f"argument '{argument_name}' expected integer but got boolean '{value}'"
        )
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(
            f"argument '{argument_name}' expected integer but got non-integer float '{value}'"
        )
    if isinstance(value, str):
        stripped = value.strip()
        if _INT_PATTERN.fullmatch(stripped):
            return int(stripped)
    raise ValueError(
        f"argument '{argument_name}' expected integer but got value of type {type(value).__name__}"
    )


def _coerce_to_number(value: Any, *, argument_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(
            f"argument '{argument_name}' expected number but got boolean '{value}'"
        )
    if isinstance(value, (int, float)):
        numeric = float(value)
        if math.isfinite(numeric):
            return numeric
        raise ValueError(
            f"argument '{argument_name}' expected finite number but got '{value}'"
        )
    if isinstance(value, str):
        stripped = value.strip()
        if _FLOAT_PATTERN.fullmatch(stripped):
            numeric = float(stripped)
            if math.isfinite(numeric):
                return numeric
    raise ValueError(
        f"argument '{argument_name}' expected number but got value of type {type(value).__name__}"
    )


def _coerce_to_boolean(value: Any, *, argument_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    raise ValueError(
        f"argument '{argument_name}' expected boolean but got value of type {type(value).__name__}"
    )


def _coerce_to_string(value: Any, *, argument_name: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        maybe_description = _extract_string_from_schema_dict(value)
        if maybe_description is not None:
            return maybe_description
    if isinstance(value, (int, float, bool)):
        return str(value)
    raise ValueError(
        f"argument '{argument_name}' expected string but got value of type {type(value).__name__}"
    )


def _coerce_value(value: Any, expected_type: str, *, argument_name: str) -> Any:
    if expected_type == "integer":
        return _coerce_to_integer(value, argument_name=argument_name)
    if expected_type == "number":
        return _coerce_to_number(value, argument_name=argument_name)
    if expected_type == "boolean":
        return _coerce_to_boolean(value, argument_name=argument_name)
    if expected_type == "string":
        return _coerce_to_string(value, argument_name=argument_name)
    return value


def normalize_tool_arguments(
    *,
    tool_name: str,
    raw_arguments: Any,
    schema_properties: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(raw_arguments, dict):
        raise ValueError(
            f"Tool '{tool_name}' expected object arguments, got {type(raw_arguments).__name__}"
        )

    if not schema_properties:
        return dict(raw_arguments)

    normalized: dict[str, Any] = {}
    for argument_name, value in raw_arguments.items():
        property_schema = schema_properties.get(argument_name, {})
        normalized[argument_name] = normalize_value(value, property_schema, argument_name)
    return normalized


def normalize_value(value, schema, path):
    # Preserve already valid values, especially int|string unions and nulls.
    try:
        validate_value(value, schema, path)
        return value
    except ValueError:
        pass
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                result = normalize_value(value, option, path)
                validate_value(result, option, path)
                return result
            except ValueError:
                continue
        raise ValueError(f"{path}: no allowed type matches")
    kind = schema.get("type")
    if kind == "array" and isinstance(value, list):
        return [normalize_value(v, schema.get("items", {}), f"{path}[{i}]") for i, v in enumerate(value)]
    if kind == "object" and isinstance(value, dict):
        extra = schema.get("additionalProperties", {})
        return {k: normalize_value(v, schema.get("properties", {}).get(k, extra if isinstance(extra, dict) else {}), f"{path}.{k}") for k, v in value.items()}
    return _coerce_value(value, kind, argument_name=path)


def validate_value(value, schema, path):
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                validate_value(value, option, path)
                return
            except ValueError:
                continue
        raise ValueError(f"{path}: no allowed type matches")
    if "enum" in schema and not any(type(value) is type(v) and value == v for v in schema["enum"]):
        raise ValueError(f"{path}: value is not in the allowed enum")
    kind = schema.get("type")
    matches = {
        "integer": type(value) is int,
        "number": type(value) in (int, float) and (not isinstance(value, float) or math.isfinite(value)),
        "boolean": type(value) is bool,
        "string": isinstance(value, str),
        "null": value is None,
        "array": isinstance(value, list),
        "object": isinstance(value, dict),
    }
    if kind is not None and not matches.get(kind, False):
        raise ValueError(f"{path}: expected {kind}, got {type(value).__name__}")
    if kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise ValueError(f"{path}: invalid array length")
        for i, item in enumerate(value):
            validate_value(item, schema.get("items", {}), f"{path}[{i}]")
    if kind == "object":
        properties = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}: missing required argument {key}")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path}: object keys must be strings")
            if key in properties:
                validate_value(item, properties[key], f"{path}.{key}")
            else:
                extra = schema.get("additionalProperties", True)
                if extra is False:
                    raise ValueError(f"{path}: unknown argument {key}")
                if isinstance(extra, dict):
                    validate_value(item, extra, f"{path}.{key}")


def validate_arguments(arguments, schema):
    validate_value(arguments, schema, "arguments")
