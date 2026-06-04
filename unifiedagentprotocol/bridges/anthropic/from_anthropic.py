# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Anthropic Tool Use -> UAP conversion.

The inverse of :mod:`to_anthropic`. Reads an Anthropic tool-use dict and
reconstructs a UAP :class:`Tool`, synthesizing a URN of the form
``urn:uap:tool:<slug>`` (derived from ``name``) and re-hydrating the
``requires_human_approval`` capability from the description prefix when
present.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

from unifiedagentprotocol.core import (
    Capabilities,
    LossInfo,
    Parameter,
    ParameterSchema,
    Tool,
)

from .to_anthropic import HUMAN_APPROVAL_PREFIX

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slugify(name: str) -> str:
    """Convert an Anthropic tool ``name`` into a URN-safe slug."""
    slug = _SLUG_RE.sub("-", name.lower()).strip("-")
    if not slug:
        slug = "tool"
    # URN slugs must start with [a-z0-9].
    if not slug[0].isalnum():
        slug = "t" + slug
    return slug


def _schema_dict_to_parameter_schema(schema: Dict[str, Any]) -> ParameterSchema:
    """Build a :class:`ParameterSchema` from a plain JSON-Schema dict."""
    return ParameterSchema.model_validate(schema)


def _parse_parameters(input_schema: Dict[str, Any]) -> list[Parameter]:
    """Turn Anthropic ``input_schema`` properties into UAP parameters."""
    properties = input_schema.get("properties", {}) or {}
    required = set(input_schema.get("required", []) or [])
    params: list[Parameter] = []
    for name, prop_schema in properties.items():
        params.append(
            Parameter(
                name=name,
                schema=_schema_dict_to_parameter_schema(prop_schema),
                required=name in required,
            )
        )
    return params


def tool_from_anthropic(obj: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Convert an Anthropic tool-use dict into a UAP :class:`Tool`.

    The Anthropic format carries no URN, so one is synthesized from
    ``name``. The ``[REQUIRES HUMAN APPROVAL]`` description prefix is
    stripped and projected back onto ``capabilities.requires_human_approval``.
    """
    if not isinstance(obj, dict):
        raise ValueError(
            f"tool_from_anthropic expects a dict; got {type(obj).__name__}."
        )

    name = obj.get("name")
    if not name:
        raise ValueError("Anthropic tool dict missing required 'name'.")
    description = obj.get("description", "")
    input_schema = obj.get("input_schema", {}) or {}

    coerced: list[str] = []
    notes: list[str] = []

    requires_approval = False
    if isinstance(description, str) and description.startswith(
        HUMAN_APPROVAL_PREFIX
    ):
        description = description[len(HUMAN_APPROVAL_PREFIX):]
        requires_approval = True
        coerced.append("capabilities.requires_human_approval")
        notes.append(
            f"Stripped '{HUMAN_APPROVAL_PREFIX.strip()}' marker from "
            "description and set capabilities.requires_human_approval."
        )

    slug = _slugify(name)
    urn = f"urn:uap:tool:{slug}"
    notes.append(f"Synthesized URN '{urn}' from tool name '{name}'.")

    parameters = _parse_parameters(input_schema)

    tool = Tool(
        id=urn,
        name=name,
        description=description,
        parameters=parameters,
        capabilities=Capabilities(requires_human_approval=requires_approval),
    )

    return tool, LossInfo(coerced_fields=coerced, notes=notes)


def from_anthropic(obj: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Public dispatcher — Anthropic tool-use dict -> UAP :class:`Tool`."""
    return tool_from_anthropic(obj)
