# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""OpenWebUI tool JSON -> UAP :class:`Tool` import."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from unifiedagentprotocol.core import (
    LossInfo,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    Tool,
    Trigger,
    TriggerType,
    UIConfig,
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


def _parameters_from_block(
    params_block: Dict[str, Any], loss: LossInfo
) -> List[Parameter]:
    out: List[Parameter] = []
    if not isinstance(params_block, dict):
        return out
    props = params_block.get("properties") or {}
    required = set(params_block.get("required") or [])
    if not isinstance(props, dict):
        return out
    for name, raw in props.items():
        if not isinstance(raw, dict):
            loss.dropped_fields.append(f"parameters.properties.{name}")
            continue
        out.append(
            Parameter(
                name=str(name),
                schema=_to_parameter_schema(raw),
                required=name in required,
                location=ParameterLocation.BODY,
                description=raw.get("description"),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Optional helpers for trigger / ui restoration
# ---------------------------------------------------------------------------

def _trigger_from_block(raw: Any) -> List[Trigger]:
    """Build at most one Trigger from the OpenWebUI ``trigger`` block."""
    if not isinstance(raw, dict):
        return []
    t_type = raw.get("type")
    try:
        trig_type = TriggerType(t_type) if isinstance(t_type, str) else None
    except ValueError:
        return []
    if trig_type is None:
        return []
    kwargs: Dict[str, Any] = {"type": trig_type}
    for k in ("cron", "intent_pattern", "webhook_path", "event_name", "description"):
        v = raw.get(k)
        if v is not None:
            kwargs[k] = v
    md = raw.get("metadata") or {}
    if isinstance(md, dict):
        kwargs["metadata"] = md
    try:
        return [Trigger(**kwargs)]
    except Exception:  # pragma: no cover — defensive
        return []


def _ui_from_block(raw: Any) -> "UIConfig | None":
    if not isinstance(raw, dict):
        return None
    label = raw.get("label") or raw.get("name") or raw.get("title")
    if not label:
        return None
    try:
        return UIConfig(
            label=str(label),
            description=raw.get("description"),
            icon=raw.get("icon"),
            color=raw.get("color"),
            group=raw.get("group"),
            order=raw.get("order"),
            locale=raw.get("locale"),
        )
    except Exception:  # pragma: no cover — defensive
        return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

_KNOWN_TOP_KEYS = {
    "id",
    "name",
    "description",
    "version",
    "parameters",
    "returns",
    "trigger",
    "ui",
}


def tool_from_openwebui(spec: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Convert an OpenWebUI tool JSON dict into a UAP :class:`Tool`."""
    if not isinstance(spec, dict):
        raise TypeError(
            f"tool_from_openwebui expected a dict, got {type(spec).__name__}"
        )
    loss = LossInfo()

    raw_id = spec.get("id")
    raw_name = spec.get("name")
    description = str(spec.get("description") or "")
    version = str(spec.get("version") or "0.1.0")

    seed = raw_id or raw_name or "tool"
    urn = f"urn:uap:tool:{_slugify(str(seed))}"

    # Tool.name must be a valid identifier; prefer raw id, fall back to slug.
    name_seed = str(raw_id or raw_name or "tool")
    name_safe = re.sub(r"[^A-Za-z0-9_]+", "_", name_seed).strip("_") or "tool"
    if name_safe[0].isdigit():
        name_safe = f"t_{name_safe}"

    display_name = str(raw_name) if raw_name else None

    parameters = _parameters_from_block(spec.get("parameters") or {}, loss)

    output = None
    returns = spec.get("returns")
    if isinstance(returns, dict):
        output = OutputSchema(schema=_to_parameter_schema(returns))

    triggers = _trigger_from_block(spec.get("trigger"))
    ui = _ui_from_block(spec.get("ui"))

    # Preserve every unknown top-level key under metadata.
    metadata: Dict[str, Any] = {}
    for k, v in spec.items():
        if k not in _KNOWN_TOP_KEYS:
            metadata[k] = v
    # Preserve original id if it differs from our slug, so to_openwebui can echo it.
    if raw_id is not None:
        metadata.setdefault("openwebui_id", raw_id)
    if raw_name is not None:
        metadata.setdefault("openwebui_name", raw_name)

    tool = Tool(
        id=urn,
        name=name_safe,
        display_name=display_name,
        description=description,
        version=version,
        parameters=parameters,
        output=output,
        triggers=triggers,
        ui=ui,
        metadata=metadata,
    )
    return tool, loss


def from_openwebui(spec: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Alias for :func:`tool_from_openwebui`."""
    return tool_from_openwebui(spec)
