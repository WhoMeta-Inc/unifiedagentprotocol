# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP -> Gemini function declaration conversion.

Gemini's ``FunctionDeclaration`` is structurally close to JSON Schema but
follows the OpenAPI 3.0 ``Schema`` convention of writing ``type`` in
uppercase (``STRING``, ``INTEGER`` …). The Gemini schema also drops
several JSON Schema features that UAP can express, notably ``format``,
``oneOf``/``anyOf``/``allOf`` and ``$ref``; those are recorded as
coerced/dropped fields.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from unifiedagentprotocol.core import (
    Agent,
    LossInfo,
    ParameterSchema,
    Tool,
)

# JSON Schema type -> Gemini OpenAPI uppercase type.
_TYPE_TO_GEMINI: Dict[str, str] = {
    "string": "STRING",
    "integer": "INTEGER",
    "number": "NUMBER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
    "object": "OBJECT",
}

# Fields that survive a UAP-ParameterSchema -> Gemini-OpenAPI conversion
# without alteration (other than the ``type`` uppercasing handled separately).
_PASSTHROUGH_FIELDS: tuple[str, ...] = (
    "description",
    "enum",
    "default",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "required",
)


def _convert_schema(
    schema: ParameterSchema, path: str, loss: LossInfo
) -> Dict[str, Any]:
    """Recursively convert a UAP ``ParameterSchema`` to a Gemini schema dict.

    Accumulates loss entries into ``loss`` (mutated in place).
    """
    raw = schema.model_dump(mode="json", exclude_none=True, by_alias=True)
    out: Dict[str, Any] = {}

    # Type — uppercase per Gemini OpenAPI convention.
    if "type" in raw:
        lower = raw["type"]
        upper = _TYPE_TO_GEMINI.get(lower)
        if upper is None:
            # 'null' is allowed by UAP but has no Gemini equivalent.
            loss.coerced_fields.append(f"{path}.type")
            loss.notes.append(
                f"Gemini has no type '{lower}'; emitted as 'STRING'."
            )
            out["type"] = "STRING"
        else:
            out["type"] = upper

    for field in _PASSTHROUGH_FIELDS:
        if field in raw:
            out[field] = raw[field]

    if "format" in raw:
        # Gemini's schema validator does not officially accept arbitrary
        # JSON Schema ``format`` values; record as coerced and pass through.
        loss.coerced_fields.append(f"{path}.format")
        loss.notes.append(
            f"Gemini does not standardise 'format' values; '{raw['format']}'"
            f" at {path} preserved as a hint only."
        )
        out["format"] = raw["format"]

    if schema.items is not None:
        out["items"] = _convert_schema(schema.items, f"{path}.items", loss)

    if schema.properties is not None:
        out["properties"] = {
            name: _convert_schema(sub, f"{path}.properties.{name}", loss)
            for name, sub in schema.properties.items()
        }

    # Composition keywords — Gemini drops these.
    for json_field, attr in (
        ("oneOf", "one_of"),
        ("anyOf", "any_of"),
        ("allOf", "all_of"),
    ):
        if getattr(schema, attr) is not None:
            loss.dropped_fields.append(f"{path}.{json_field}")
            loss.notes.append(
                f"Gemini schema does not support '{json_field}'; dropped at "
                f"{path}."
            )

    if schema.ref is not None:
        loss.dropped_fields.append(f"{path}.$ref")
        loss.notes.append(
            f"Gemini schema does not support '$ref'; dropped at {path}."
        )

    # Preserve x-uap-* extensions on a best-effort basis.
    for key, value in raw.items():
        if key.startswith("x-"):
            out[key] = value

    return out


def _build_parameters(uap_tool: Tool, loss: LossInfo) -> Dict[str, Any]:
    """Assemble the Gemini ``parameters`` schema from a UAP Tool."""
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for param in uap_tool.parameters:
        properties[param.name] = _convert_schema(
            param.schema_, f"parameters.{param.name}.schema", loss
        )
        if param.required:
            required.append(param.name)
    out: Dict[str, Any] = {"type": "OBJECT", "properties": properties}
    if required:
        out["required"] = required
    return out


def tool_to_gemini(uap_tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Tool` into a Gemini ``FunctionDeclaration`` dict."""
    loss = LossInfo()
    parameters = _build_parameters(uap_tool, loss)

    out: Dict[str, Any] = {
        "name": uap_tool.name,
        "description": uap_tool.description,
        "parameters": parameters,
    }

    # Record dropped UAP envelope fields.
    if uap_tool.triggers:
        loss.dropped_fields.append("triggers")
    if uap_tool.endpoint is not None:
        loss.dropped_fields.append("endpoint")
    if uap_tool.auth is not None:
        loss.dropped_fields.append("auth")
    loss.dropped_fields.append("capabilities")
    loss.dropped_fields.append("compliance")
    if uap_tool.cost is not None:
        loss.dropped_fields.append("cost")
    if uap_tool.ui is not None:
        loss.dropped_fields.append("ui")
    if uap_tool.output is not None:
        loss.dropped_fields.append("output")
        loss.notes.append(
            "Gemini FunctionDeclaration carries no output schema; the "
            "tool's response shape is implicit at invocation time."
        )

    loss.notes.append(
        "Gemini function declarations omit UAP's enterprise envelope "
        "(triggers, endpoint, auth, capabilities, compliance, cost)."
    )

    return out, loss


def to_gemini(obj: Any) -> Tuple[Dict[str, Any], LossInfo]:
    """Dispatch a UAP object to the Gemini function-declaration format.

    Only :class:`Tool` is supported. Agent-level Gemini concepts
    (multi-tool ``ToolConfig``, system instructions) are out of scope.
    """
    if isinstance(obj, Agent):
        raise ValueError(
            "Gemini function declarations are tool-level only; "
            "an Agent cannot be converted. Convert its individual tools "
            "with tool_to_gemini() instead."
        )
    if isinstance(obj, Tool):
        return tool_to_gemini(obj)
    raise ValueError(
        f"to_gemini expects a Tool; got {type(obj).__name__}."
    )
