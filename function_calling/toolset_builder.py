"""
Tool discovery adapted from FarmAgent rsare/agents/agent/toolset_builder.py.

This module intentionally avoids a hard dependency on `openai-agents`.
It generates OpenAI-compatible function schemas from Python signatures.
"""

from __future__ import annotations

import inspect
import re
import types
import typing
from typing import Any, Callable, get_args, get_origin


def agent_tool(func=None, *, doc_enabled=True):
    def decorator(f):
        f.is_agent_tool = True
        if not (doc_enabled):
            f.__doc__ = ""  # Strips the docstring at runtime
        return f
    return decorator if func is None else decorator(func)


def agent_toolset(obj) -> list:
    """
    Returns a list with callable methods that are marked with
    the 'is_agent_tool' attribute on the given object.

    Args:
        obj: The object (typically an agent instance) to inspect.

    Returns:
        A list where items callable methods.
    """
    # FIX: accept either an instance or a class, and if it's a class, instantiate it once
    if isinstance(obj, type):   # it's a class
        obj = obj()             # instantiate once

    tools = []
    for attr_name in dir(obj):
        attr = getattr(obj, attr_name)
        if callable(attr) and getattr(attr, "is_agent_tool", False):
            tools.append(attr)
    return tools


def _annotation_to_json_schema(annotation: Any) -> dict[str, Any]:
    if annotation in (inspect.Signature.empty, Any):
        return {}
    if isinstance(annotation, str):
        normalized = annotation.strip().lower()
        if normalized in {"str", "string"}:
            return {"type": "string"}
        if normalized in {"int", "integer"}:
            return {"type": "integer"}
        if normalized in {"float", "number"}:
            return {"type": "number"}
        if normalized in {"bool", "boolean"}:
            return {"type": "boolean"}
        raise TypeError(f"Unresolved tool annotation: {annotation}")

    origin = get_origin(annotation)
    args = get_args(annotation)

    if annotation is type(None):
        return {"type": "null"}
    if origin is typing.Literal:
        return {"enum": list(args)}

    if origin is None:
        if annotation is str:
            return {"type": "string"}
        if annotation is int:
            return {"type": "integer"}
        if annotation is float:
            return {"type": "number"}
        if annotation is bool:
            return {"type": "boolean"}
        if annotation is dict:
            return {"type": "object"}
        if annotation is list:
            return {"type": "array", "items": {}}
        raise TypeError(f"Unsupported tool annotation: {annotation}")

    if origin is tuple and args and len(set(args)) == 1:
        return {"type": "array", "items": _annotation_to_json_schema(args[0]),
                "minItems": len(args), "maxItems": len(args)}

    if origin is list:
        item_type = args[0] if args else Any
        return {"type": "array", "items": _annotation_to_json_schema(item_type)}

    if origin is dict:
        if args and args[0] not in (str, Any):
            raise TypeError("JSON object keys must be strings")
        return {"type": "object", "additionalProperties": _annotation_to_json_schema(args[1]) if args else {}}

    if origin in (typing.Union, types.UnionType):
        return {"anyOf": [_annotation_to_json_schema(arg) for arg in args]}

    raise TypeError(f"Unsupported tool annotation: {annotation}")


def build_tool_schema(func: Callable) -> dict:
    signature = inspect.signature(func)
    hints = typing.get_type_hints(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, parameter in signature.parameters.items():
        if param_name in {"self", "cls"}:
            continue
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise TypeError(f"Tool {func.__name__} requires named, fixed parameters")
        properties[param_name] = _annotation_to_json_schema(hints.get(param_name, parameter.annotation))
        if parameter.default is inspect.Parameter.empty:
            required.append(param_name)

    parameters_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        parameters_schema["required"] = required

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": inspect.getdoc(func) or "",
            "parameters": parameters_schema,
        },
    }


def build_toolset(toolsets, *, tools=None):

    assert isinstance(toolsets, list)
    registrations = dict(tools or {})
    # Aggregate all tools from the provided toolset objects.
    tools = []
    tool_to_app_name = {}
    for toolset in toolsets:
        if isinstance(toolset, type):
            toolset = toolset()
        toolset_list = agent_toolset(toolset)
        # Track which app each tool belongs to
        app_name = getattr(toolset, 'name', toolset.__class__.__name__)
        for tool in toolset_list:
            tool_to_app_name[tool] = app_name
        # We add the tool callables to our aggregated list.
        tools.extend(toolset_list)
    # turn python functions into tools and save a reverse map
    # following: https://cookbook.openai.com/examples/orchestrating_agents
    # Explicit name -> callable registrations let CORE expose its existing tool
    # set without modifying world classes or discovering private setup helpers.
    tool_schemas = []
    tools_map = {}
    for tool in tools:
        app_name = tool_to_app_name[tool]
        original_name = tool.__name__
        # Prefix tool name with app name to ensure uniqueness
        prefixed_name = f"{app_name}__{original_name}"
        if prefixed_name in registrations:
            raise ValueError(f"Duplicate tool name: {prefixed_name}")
        registrations[prefixed_name] = tool
    for name, tool in registrations.items():
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            raise ValueError(f"Invalid tool name: {name}")
        if not callable(tool):
            raise TypeError(f"Tool {name} is not callable")
        schema = build_tool_schema(tool)
        schema["function"]["name"] = name
        tool_schemas.append(schema)
        tools_map[name] = tool

    return list(tools_map.values()), tool_schemas, tools_map
