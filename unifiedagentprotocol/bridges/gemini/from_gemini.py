# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Gemini function declaration -> UAP conversion.

Reads a Gemini ``FunctionDeclaration`` dict and reconstructs a UAP
:class:`Tool`. The OpenAPI-style uppercase ``type`` values are mapped
back to their lowercase JSON Schema counterparts.

As with the Anthropic bridge, no URN is present in the source format, so
one is synthesized from the function name.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from unifiedagentprotocol.core import (
    LossInfo,
    Parameter,
    ParameterSchema,
    Tool,
)

_GEMINI_TO_JSON: Dict[str, str] = {
    "STRING": "string",
    "INTEGER": "integer",
    "NUMBER": "number",
    "BOOLEAN": "boolean",
    "ARRAY": "array",
    "OBJECT": "object",
}

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        slug = "tool"
    if not slug[0].isalnum():
        slug = "t" + slug
    return slug


def _convert_schema(
    schema: Dict[str, Any], path: str, loss: LossInfo
) -> Dict[str, Any]:
    """Recursively convert a Gemini schema dict to JSON-Schema-shaped dict."""
    out: Dict[str, Any] = dict(schema)  # shallow copy

    if "type" in out:
        upper = out["type"]
        if isinstance(upper, str):
            lower = _GEMINI_TO_JSON.get(upper.upper())
            if lower is None:
                loss.coerced_fields.append(f"{path}.type")
                loss.notes.append(
                    f"Unknown Gemini type '{upper}' at {path}; "
                    "coerced to 'string'."
                )
                out["type"] = "string"
            else:
                out["type"] = lower

    if "items" in out and isinstance(out["items"], dict):
        out["items"] = _convert_schema(
            out["items"], f"{path}.items", loss
        )

    if "properties" in out and isinstance(out["properties"], dict):
        out["properties"] = {
            name: _convert_schema(sub, f"{path}.properties.{name}", loss)
            for name, sub in out["properties"].items()
        }

    return out


def _parse_parameters(parameters: Dict[str, Any], loss: LossInfo) -> list[Parameter]:
    properties = parameters.get("properties", {}) or {}
    required = set(parameters.get("required", []) or [])
    params: list[Parameter] = []
    for name, prop_schema in properties.items():
        converted = _convert_schema(
            prop_schema, f"parameters.{name}.schema", loss
        )
        schema = ParameterSchema.model_validate(converted)
        params.append(
            Parameter(name=name, schema=schema, required=name in required)
        )
    return params


def tool_from_gemini(obj: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Convert a Gemini ``FunctionDeclaration`` dict into a UAP :class:`Tool`."""
    if not isinstance(obj, dict):
        raise ValueError(
            f"tool_from_gemini expects a dict; got {type(obj).__name__}."
        )

    name = obj.get("name")
    if not name:
        raise ValueError("Gemini function declaration missing required 'name'.")
    description = obj.get("description", "")
    parameters_obj = obj.get("parameters", {}) or {}

    loss = LossInfo()
    parameters = _parse_parameters(parameters_obj, loss)

    slug = _slugify(name)
    urn = f"urn:uap:tool:{slug}"
    loss.notes.append(
        f"Synthesized URN '{urn}' from function name '{name}'."
    )

    tool = Tool(
        id=urn,
        name=name,
        description=description,
        parameters=parameters,
    )

    return tool, loss


def from_gemini(obj: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Public dispatcher — Gemini function-decl dict -> UAP :class:`Tool`."""
    return tool_from_gemini(obj)
