# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP :class:`Tool` -> OpenWebUI tool JSON export."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from unifiedagentprotocol.core import (
    LossInfo,
    Parameter,
    ParameterLocation,
    Tool,
)


# Top-level keys that come from the OpenWebUI surface itself; the rest of
# Tool.metadata is treated as "unknown" and re-emitted verbatim.
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

_METADATA_RESERVED = {"openwebui_id", "openwebui_name"}


def _schema_dict(param: Parameter) -> Dict[str, Any]:
    data = param.schema_.model_dump(mode="json", exclude_none=True, by_alias=True)
    if param.description and "description" not in data:
        data["description"] = param.description
    return data


def _parameters_block(tool: Tool, loss: LossInfo) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for idx, p in enumerate(tool.parameters):
        if p.location is not ParameterLocation.BODY:
            loss.coerced_fields.append(f"parameters[{idx}].location")
            loss.notes.append(
                f"Parameter {p.name!r} location={p.location.value!r} cannot be "
                "expressed by OpenWebUI; folded into body."
            )
        properties[p.name] = _schema_dict(p)
        if p.required:
            required.append(p.name)
    block: Dict[str, Any] = {"properties": properties}
    if required:
        block["required"] = required
    return block


def tool_to_openwebui(tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Tool` into an OpenWebUI tool dict."""
    loss = LossInfo()
    md = dict(tool.metadata or {})

    # Recover original id/name fields if from_openwebui smuggled them in.
    raw_id = md.pop("openwebui_id", None) or tool.id.rsplit(":", 1)[-1]
    raw_name = md.pop("openwebui_name", None) or tool.display_name or tool.name

    out: Dict[str, Any] = {
        "id": raw_id,
        "name": raw_name,
        "description": tool.description,
    }
    if tool.version and tool.version != "0.1.0":
        out["version"] = tool.version
    if tool.parameters:
        out["parameters"] = _parameters_block(tool, loss)
    else:
        out["parameters"] = {"properties": {}}
    if tool.output is not None:
        out["returns"] = tool.output.schema_.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    if tool.triggers:
        # OpenWebUI surfaces a single trigger; emit the first.
        first = tool.triggers[0]
        out["trigger"] = first.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
        if len(tool.triggers) > 1:
            loss.dropped_fields.append("triggers[1:]")
            loss.notes.append(
                "OpenWebUI has a single trigger slot; only triggers[0] was kept."
            )
    if tool.ui is not None:
        out["ui"] = tool.ui.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )

    # UAP-only fields with no OpenWebUI home -> record loss explicitly.
    if tool.auth is not None:
        loss.dropped_fields.append("auth")
        loss.notes.append("OpenWebUI tools do not declare auth; dropped.")
    if tool.endpoint is not None:
        loss.dropped_fields.append("endpoint")
        loss.notes.append("OpenWebUI tools do not declare endpoint; dropped.")
    if tool.cost is not None:
        loss.dropped_fields.append("cost")
    if tool.tags:
        loss.dropped_fields.append("tags")
        loss.notes.append("OpenWebUI has no tag list; preserved as metadata only.")
    # capabilities & compliance always present (defaults) — declare lossy.
    loss.dropped_fields.append("capabilities")
    loss.dropped_fields.append("compliance")

    # Surface any remaining unknown metadata at the top level.
    for k, v in md.items():
        if k in _METADATA_RESERVED:
            continue
        if k not in _KNOWN_TOP_KEYS and k not in out:
            out[k] = v

    return out, loss


def to_openwebui(obj: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Public dispatcher. Only Tools are supported by OpenWebUI."""
    if isinstance(obj, Tool):
        return tool_to_openwebui(obj)
    raise TypeError(
        f"to_openwebui expects a Tool; got {type(obj).__name__}"
    )
