# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP -> Anthropic Tool Use conversion.

Anthropic represents a callable tool as a flat dict with three top-level
keys: ``name``, ``description`` and ``input_schema`` (JSON Schema for the
arguments). It does not surface any of UAP's enterprise envelope
(triggers, endpoint, auth, capabilities, compliance, cost), so those
fields are recorded as losses.

The ``requires_human_approval`` capability is smuggled through the
description as a leading ``[REQUIRES HUMAN APPROVAL] `` marker so it
survives a round-trip.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from unifiedagentprotocol.core import Agent, LossInfo, Parameter, Tool

HUMAN_APPROVAL_PREFIX = "[REQUIRES HUMAN APPROVAL] "


def _parameter_to_schema_dict(param: Parameter) -> Dict[str, Any]:
    """Dump the JSON-Schema portion of a UAP ``Parameter`` to a plain dict."""
    return param.schema_.model_dump(
        mode="json", exclude_none=True, by_alias=True
    )


def _build_input_schema(uap_tool: Tool) -> Dict[str, Any]:
    """Assemble Anthropic ``input_schema`` (a JSON Schema object) from UAP."""
    properties: Dict[str, Any] = {}
    required: list[str] = []
    for param in uap_tool.parameters:
        properties[param.name] = _parameter_to_schema_dict(param)
        if param.required:
            required.append(param.name)
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def tool_to_anthropic(uap_tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP ``Tool`` into an Anthropic tool-use dict.

    Returns the tool dict and a :class:`LossInfo` documenting which UAP
    fields were dropped or coerced.
    """
    dropped: list[str] = []
    coerced: list[str] = []
    notes: list[str] = []

    description = uap_tool.description
    if uap_tool.capabilities.requires_human_approval:
        description = HUMAN_APPROVAL_PREFIX + description
        coerced.append("capabilities.requires_human_approval")
        notes.append(
            "capabilities.requires_human_approval surfaced as a "
            f"'{HUMAN_APPROVAL_PREFIX.strip()}' prefix on description."
        )

    out: Dict[str, Any] = {
        "name": uap_tool.name,
        "description": description,
        "input_schema": _build_input_schema(uap_tool),
    }

    # Drop everything Anthropic's tool-use schema cannot express.
    if uap_tool.triggers:
        dropped.append("triggers")
    if uap_tool.endpoint is not None:
        dropped.append("endpoint")
    if uap_tool.auth is not None:
        dropped.append("auth")
    # Capabilities are dropped wholesale (except for the smuggled flag above).
    dropped.append("capabilities")
    dropped.append("compliance")
    if uap_tool.cost is not None:
        dropped.append("cost")
    if uap_tool.ui is not None:
        dropped.append("ui")
    if uap_tool.output is not None:
        dropped.append("output")
        notes.append(
            "Anthropic tool-use carries no output schema; the tool's "
            "response shape is implicit at invocation time."
        )

    notes.append(
        "Anthropic tool-use format omits UAP's enterprise envelope "
        "(triggers, endpoint, auth, capabilities, compliance, cost)."
    )

    return out, LossInfo(
        dropped_fields=dropped, coerced_fields=coerced, notes=notes
    )


def to_anthropic(obj: Any) -> Tuple[Dict[str, Any], LossInfo]:
    """Dispatch a UAP object to the Anthropic tool-use format.

    Only :class:`Tool` is supported. Anthropic has no agent-level concept,
    so :class:`Agent` inputs raise ``ValueError``.
    """
    if isinstance(obj, Agent):
        raise ValueError(
            "Anthropic Tool Use has no agent-level concept; "
            "an Agent cannot be converted. Convert its individual tools "
            "with tool_to_anthropic() instead."
        )
    if isinstance(obj, Tool):
        return tool_to_anthropic(obj)
    raise ValueError(
        f"to_anthropic expects a Tool; got {type(obj).__name__}."
    )
