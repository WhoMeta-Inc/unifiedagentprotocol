# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""LangChain tool dict -> UAP :class:`Tool` import."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from unifiedagentprotocol.core import (
    LossInfo,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    Tool,
)
from unifiedagentprotocol.core.schema.tool import OutputSchema


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

_SLUG_INVALID = re.compile(r"[^a-z0-9._-]+")
_SLUG_DASH = re.compile(r"-{2,}")


def _slugify(raw: str) -> str:
    lowered = (raw or "").strip().lower()
    slug = _SLUG_INVALID.sub("-", lowered)
    slug = _SLUG_DASH.sub("-", slug)
    slug = slug.strip("-._")
    return slug or "unnamed"


# ---------------------------------------------------------------------------
# Schema conversion
# ---------------------------------------------------------------------------

_SCHEMA_KEYS = {
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
    "required",
    "oneOf",
    "anyOf",
    "allOf",
    "$ref",
}


def _to_parameter_schema(obj: Any) -> ParameterSchema:
    if not isinstance(obj, dict):
        return ParameterSchema()
    data: Dict[str, Any] = {}
    for k, v in obj.items():
        if k in _SCHEMA_KEYS:
            if k == "items" and isinstance(v, dict):
                data[k] = _to_parameter_schema(v).model_dump(
                    mode="json", exclude_none=True, by_alias=True
                )
            elif k == "properties" and isinstance(v, dict):
                data[k] = {
                    pk: _to_parameter_schema(pv).model_dump(
                        mode="json", exclude_none=True, by_alias=True
                    )
                    for pk, pv in v.items()
                }
            else:
                data[k] = v
        elif k.startswith("x-"):
            data[k] = v
    return ParameterSchema(**data)


def _parameter_from_args_entry(
    name: str, raw: Dict[str, Any], loss: LossInfo
) -> Parameter:
    """Translate one ``args_schema[name] = {...}`` entry into a UAP Parameter.

    Note: at the LangChain entry level, ``required`` is a *boolean* flag for
    the parameter itself (not the JSON-Schema ``required`` array). We strip
    it from the schema dict so :class:`ParameterSchema` does not try to
    validate ``required: True`` as a list of strings. The JSON-Schema
    list-form is preserved under the ``properties_required`` alias
    introduced by :func:`tool_to_langchain`.
    """
    schema_data: Dict[str, Any] = {}
    for k in _SCHEMA_KEYS:
        if k == "required":
            continue
        if k in raw:
            schema_data[k] = raw[k]
    if isinstance(raw.get("properties_required"), list):
        schema_data["required"] = raw["properties_required"]
    schema = _to_parameter_schema(schema_data)
    required = bool(raw.get("required", True))
    return Parameter(
        name=name,
        schema=schema,
        required=required,
        location=ParameterLocation.BODY,
        description=raw.get("description"),
    )


_KNOWN_TOP_KEYS = {
    "name",
    "description",
    "version",
    "args_schema",
    "return_schema",
    "id",
}


def tool_from_langchain(spec: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Parse a LangChain tool dict into a UAP :class:`Tool`."""
    if not isinstance(spec, dict):
        raise TypeError(
            f"tool_from_langchain expected a dict, got {type(spec).__name__}"
        )
    loss = LossInfo()

    raw_name = spec.get("name")
    description = str(spec.get("description") or "")
    version = str(spec.get("version") or "0.1.0")
    raw_id = spec.get("id")

    seed = raw_id or raw_name or "tool"
    urn = f"urn:uap:tool:{_slugify(str(seed))}"

    name_seed = str(raw_name or raw_id or "tool")
    name_safe = re.sub(r"[^A-Za-z0-9_]+", "_", name_seed).strip("_") or "tool"
    if name_safe[0].isdigit():
        name_safe = f"t_{name_safe}"

    # args_schema -> parameters
    args = spec.get("args_schema") or {}
    parameters: List[Parameter] = []
    if isinstance(args, dict):
        for name, raw in args.items():
            if not isinstance(raw, dict):
                loss.dropped_fields.append(f"args_schema.{name}")
                continue
            parameters.append(_parameter_from_args_entry(str(name), raw, loss))

    # return_schema -> output
    output = None
    ret = spec.get("return_schema")
    if isinstance(ret, dict):
        output = OutputSchema(schema=_to_parameter_schema(ret))

    # Preserve unknown top-level keys + smuggled identity for to_langchain.
    metadata: Dict[str, Any] = {}
    for k, v in spec.items():
        if k not in _KNOWN_TOP_KEYS:
            metadata[k] = v
    if raw_name is not None:
        metadata.setdefault("langchain_name", raw_name)
    if raw_id is not None:
        metadata.setdefault("langchain_id", raw_id)

    tool = Tool(
        id=urn,
        name=name_safe,
        description=description,
        version=version,
        parameters=parameters,
        output=output,
        metadata=metadata,
    )
    return tool, loss


def from_langchain(spec: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Alias for :func:`tool_from_langchain`."""
    return tool_from_langchain(spec)
