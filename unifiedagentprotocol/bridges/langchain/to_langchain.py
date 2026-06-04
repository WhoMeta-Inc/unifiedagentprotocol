# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP :class:`Tool` -> LangChain tool dict export."""
from __future__ import annotations

from typing import Any, Dict, Tuple

from unifiedagentprotocol.core import (
    LossInfo,
    Parameter,
    ParameterLocation,
    Tool,
)


_KNOWN_TOP_KEYS = {
    "name",
    "description",
    "version",
    "args_schema",
    "return_schema",
    "id",
}

_METADATA_RESERVED = {"langchain_name", "langchain_id"}


def _arg_entry(param: Parameter) -> Dict[str, Any]:
    """Translate a UAP Parameter into one LangChain ``args_schema`` value.

    Note: the entry-level ``required`` key encodes whether the parameter
    itself is required (boolean). The JSON-Schema ``required`` array — only
    meaningful for ``type=object`` schemas — is preserved as
    ``properties_required`` to avoid the boolean/list collision.
    """
    raw = param.schema_.model_dump(mode="json", exclude_none=True, by_alias=True)
    entry: Dict[str, Any] = {}
    for k in (
        "type",
        "description",
        "format",
        "enum",
        "default",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "items",
        "properties",
        "oneOf",
        "anyOf",
        "allOf",
        "$ref",
    ):
        if k in raw:
            entry[k] = raw[k]
    if "required" in raw and isinstance(raw["required"], list):
        entry["properties_required"] = raw["required"]
    # The parameter-level description takes precedence if absent.
    if param.description and "description" not in entry:
        entry["description"] = param.description
    entry["required"] = bool(param.required)
    return entry


def tool_to_langchain(tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Tool` into a LangChain tool-dict."""
    loss = LossInfo()
    md = dict(tool.metadata or {})

    raw_name = md.pop("langchain_name", None) or tool.name
    raw_id = md.pop("langchain_id", None)

    out: Dict[str, Any] = {
        "name": raw_name,
        "description": tool.description,
    }
    if raw_id is not None:
        out["id"] = raw_id
    if tool.version and tool.version != "0.1.0":
        out["version"] = tool.version

    args_schema: Dict[str, Any] = {}
    for idx, p in enumerate(tool.parameters):
        if p.location is not ParameterLocation.BODY:
            loss.coerced_fields.append(f"parameters[{idx}].location")
            loss.notes.append(
                f"Parameter {p.name!r} location={p.location.value!r} cannot be "
                "expressed by LangChain; folded into args_schema body."
            )
        args_schema[p.name] = _arg_entry(p)
    out["args_schema"] = args_schema

    if tool.output is not None:
        out["return_schema"] = tool.output.schema_.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )

    # UAP-only envelope -> declared as loss.
    if tool.auth is not None:
        loss.dropped_fields.append("auth")
    if tool.endpoint is not None:
        loss.dropped_fields.append("endpoint")
    if tool.cost is not None:
        loss.dropped_fields.append("cost")
    if tool.triggers:
        loss.dropped_fields.append("triggers")
    if tool.ui is not None:
        loss.dropped_fields.append("ui")
    if tool.tags:
        loss.dropped_fields.append("tags")
    loss.dropped_fields.append("capabilities")
    loss.dropped_fields.append("compliance")

    # Surface unknown metadata at the top level.
    for k, v in md.items():
        if k in _METADATA_RESERVED:
            continue
        if k not in _KNOWN_TOP_KEYS and k not in out:
            out[k] = v

    return out, loss


def to_langchain(obj: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Public dispatcher. LangChain bridge supports Tools only."""
    if isinstance(obj, Tool):
        return tool_to_langchain(obj)
    raise TypeError(
        f"to_langchain expects a Tool; got {type(obj).__name__}"
    )
