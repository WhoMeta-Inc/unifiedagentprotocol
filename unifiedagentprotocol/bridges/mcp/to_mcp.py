# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Convert UAP objects to MCP (Model Context Protocol) descriptors.

Mapping rules
-------------

UAP ``Tool`` -> MCP Tool object::

    {
      "name":        Tool.name,
      "description": Tool.description,
      "inputSchema": { JSON Schema object built from Tool.parameters },
      "annotations": {
        "title":            Tool.display_name,        # optional
        "x-uap-id":         Tool.id,
        "x-uap-version":    Tool.version,
        "x-uap-tags":       Tool.tags,
        "x-uap-metadata":   Tool.metadata,
        "x-uap-output":     Tool.output.schema,       # optional
        "x-uap-endpoint":   {transport, url, method}, # only http / stdio
        "x-uap-auth":       {type, scopes, ...},      # only none/bearer/api_key
        "x-uap-capabilities": Capabilities.model_dump(...),
        "x-uap-compliance":   Compliance.model_dump(...) minus data_residency,
        "x-uap-cost":         CostHint.model_dump(...),
        "x-uap-ui":           UIConfig.model_dump(...),
      }
    }

UAP ``Agent`` -> MCP server descriptor::

    {
      "name":        Agent.name,
      "version":     Agent.version,
      "description": Agent.description,
      "tools":     [ to_mcp(tool) for tool in Agent.tools ],
      "resources": [],
      "prompts":   [],
      "annotations": {
        "title":            Agent.display_name,
        "x-uap-id":         Agent.id,
        "x-uap-skills":     [Skill.model_dump() ...],
        "x-uap-endpoints":  [Endpoint.model_dump() ...] (filtered),
        "x-uap-auth":       AuthConfig.model_dump() (filtered),
        "x-uap-capabilities": Capabilities.model_dump(),
        "x-uap-compliance":   Compliance.model_dump() minus data_residency,
        "x-uap-ui":           UIConfig.model_dump(),
        "x-uap-tags":         Agent.tags,
        "x-uap-metadata":     Agent.metadata,
        "x-uap-publisher":    Agent.publisher,
        "x-uap-homepage":     Agent.homepage,
        "x-uap-documentation-url": Agent.documentation_url,
      }
    }

Lossy fields (recorded in :class:`LossInfo`)
- ``triggers``               (MCP has no trigger concept)
- ``endpoint.transport``     when not in {``http``, ``stdio``}
- ``auth.type``              when not in {``none``, ``bearer``, ``api_key``}
- ``compliance.data_residency``
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Union

from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    Capabilities,
    Compliance,
    CostHint,
    Endpoint,
    LossInfo,
    Parameter,
    ParameterLocation,
    Tool,
    UIConfig,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: MCP transports we can faithfully represent in ``x-uap-endpoint``.
_MCP_REPRESENTABLE_TRANSPORTS: frozenset[str] = frozenset({"http", "stdio"})

#: AuthConfig types we can faithfully represent in ``x-uap-auth``.
_MCP_REPRESENTABLE_AUTH: frozenset[str] = frozenset({"none", "bearer", "api_key"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _dump(obj: Any) -> Any:
    """Serialise a pydantic model with UAP wire conventions."""
    return obj.model_dump(mode="json", exclude_none=True, by_alias=True)


def _parameter_to_json_schema(param: Parameter) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Return ``(json_schema, uap_annotations)`` for one Parameter.

    The first element is the raw JSON-Schema fragment that goes into
    ``inputSchema.properties[name]``. The second element is the UAP
    metadata (``required`` flag is handled by the caller; the
    ``location``/``description`` overrides surface here so they can be
    round-tripped via ``inputSchema.x-uap-parameters``).
    """
    schema = _dump(param.schema_)
    meta: Dict[str, Any] = {"name": param.name}
    if param.location != ParameterLocation.BODY:
        meta["location"] = param.location.value
    if param.description is not None:
        meta["description"] = param.description
    # ``required`` is handled by the parent inputSchema.required[] array.
    meta["required"] = bool(param.required)
    return schema, meta


def _build_input_schema(
    parameters: List[Parameter],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Return ``(inputSchema, uap_parameter_metadata)``.

    ``inputSchema`` is always a JSON-Schema ``object`` with ``properties``
    and ``required`` arrays, even when there are no parameters (MCP
    clients expect a valid schema object).
    """
    properties: Dict[str, Any] = {}
    required: List[str] = []
    uap_meta: List[Dict[str, Any]] = []

    for param in parameters:
        schema, meta = _parameter_to_json_schema(param)
        properties[param.name] = schema
        if param.required:
            required.append(param.name)
        uap_meta.append(meta)

    input_schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    return input_schema, uap_meta


def _capabilities_payload(caps: Capabilities) -> Dict[str, Any]:
    """Serialise Capabilities into a JSON-friendly dict."""
    return _dump(caps)


def _compliance_payload(comp: Compliance) -> Tuple[Dict[str, Any], bool]:
    """Return ``(serialised, dropped_residency)``.

    ``data_residency`` cannot be represented in MCP and is excluded from
    the serialised form; the bool flag tells the caller whether it was
    actually present (non-empty).
    """
    data = _dump(comp)
    dropped = False
    if data.get("data_residency"):
        dropped = True
    data.pop("data_residency", None)
    return data, dropped


def _cost_payload(cost: CostHint) -> Dict[str, Any]:
    return _dump(cost)


def _ui_payload(ui: UIConfig) -> Dict[str, Any]:
    return _dump(ui)


def _endpoint_payload(
    endpoint: Endpoint, prefix: str, losses: LossInfo
) -> Dict[str, Any] | None:
    """Serialise an Endpoint, recording loss for non-representable transports.

    Returns ``None`` when the transport is unrepresentable in MCP, in
    which case the entire endpoint object is dropped (the loss is
    recorded under ``prefix``).
    """
    transport = endpoint.transport.value
    if transport not in _MCP_REPRESENTABLE_TRANSPORTS:
        losses.dropped_fields.append(prefix)
        losses.notes.append(
            f"MCP does not model transport={transport!r}; endpoint dropped."
        )
        return None
    return _dump(endpoint)


def _auth_payload(
    auth: AuthConfig, prefix: str, losses: LossInfo
) -> Dict[str, Any] | None:
    """Serialise an AuthConfig, dropping non-representable auth types.

    Returns ``None`` when the auth type is unrepresentable; the loss is
    recorded under ``prefix`` and a note is appended.
    """
    auth_type = auth.type.value
    if auth_type not in _MCP_REPRESENTABLE_AUTH:
        losses.dropped_fields.append(prefix)
        losses.notes.append(
            f"MCP does not model auth.type={auth_type!r}; auth config dropped."
        )
        return None
    return _dump(auth)


def _record_trigger_losses(
    triggers: List[Any], prefix: str, losses: LossInfo
) -> None:
    """Record that all triggers were dropped (MCP has no trigger concept)."""
    if not triggers:
        return
    for index, _ in enumerate(triggers):
        losses.dropped_fields.append(f"{prefix}[{index}]")
    losses.notes.append(
        "MCP has no trigger concept; all UAP triggers were dropped."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def tool_to_mcp(uap_tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Tool` to an MCP Tool object."""
    losses = LossInfo()

    input_schema, uap_parameter_meta = _build_input_schema(uap_tool.parameters)

    annotations: Dict[str, Any] = {
        "x-uap-id": uap_tool.id,
        "x-uap-version": uap_tool.version,
    }

    if uap_tool.display_name is not None:
        # MCP convention: human-readable title.
        annotations["title"] = uap_tool.display_name

    if uap_parameter_meta:
        annotations["x-uap-parameters"] = uap_parameter_meta

    if uap_tool.output is not None:
        annotations["x-uap-output"] = _dump(uap_tool.output)

    if uap_tool.endpoint is not None:
        endpoint_payload = _endpoint_payload(
            uap_tool.endpoint, "endpoint", losses
        )
        if endpoint_payload is not None:
            annotations["x-uap-endpoint"] = endpoint_payload

    if uap_tool.triggers:
        _record_trigger_losses(uap_tool.triggers, "triggers", losses)

    if uap_tool.auth is not None:
        auth_payload = _auth_payload(uap_tool.auth, "auth", losses)
        if auth_payload is not None:
            annotations["x-uap-auth"] = auth_payload

    annotations["x-uap-capabilities"] = _capabilities_payload(
        uap_tool.capabilities
    )

    compliance_payload, residency_dropped = _compliance_payload(
        uap_tool.compliance
    )
    annotations["x-uap-compliance"] = compliance_payload
    if residency_dropped:
        losses.dropped_fields.append("compliance.data_residency")
        losses.notes.append(
            "MCP does not model compliance.data_residency; field dropped."
        )

    if uap_tool.cost is not None:
        annotations["x-uap-cost"] = _cost_payload(uap_tool.cost)

    if uap_tool.ui is not None:
        annotations["x-uap-ui"] = _ui_payload(uap_tool.ui)

    if uap_tool.tags:
        annotations["x-uap-tags"] = list(uap_tool.tags)
    if uap_tool.metadata:
        annotations["x-uap-metadata"] = dict(uap_tool.metadata)

    mcp_tool: Dict[str, Any] = {
        "name": uap_tool.name,
        "description": uap_tool.description,
        "inputSchema": input_schema,
        "annotations": annotations,
    }
    return mcp_tool, losses


def agent_to_mcp(uap_agent: Agent) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Agent` to an MCP server descriptor."""
    losses = LossInfo()

    # Tools: inline Tool objects are converted; URN strings pass through
    # via the annotations.x-uap-tool-refs list (they are *references*, not
    # full tools, so they cannot appear in the MCP ``tools`` array).
    mcp_tools: List[Dict[str, Any]] = []
    tool_refs: List[str] = []
    for index, item in enumerate(uap_agent.tools):
        if isinstance(item, Tool):
            mcp_tool, tool_losses = tool_to_mcp(item)
            mcp_tools.append(mcp_tool)
            # Prefix nested losses so callers can locate them.
            for field in tool_losses.dropped_fields:
                losses.dropped_fields.append(f"tools[{index}].{field}")
            for field in tool_losses.coerced_fields:
                losses.coerced_fields.append(f"tools[{index}].{field}")
            losses.notes.extend(tool_losses.notes)
        else:
            tool_refs.append(item)

    annotations: Dict[str, Any] = {
        "x-uap-id": uap_agent.id,
    }
    if uap_agent.display_name is not None:
        annotations["title"] = uap_agent.display_name
    if tool_refs:
        annotations["x-uap-tool-refs"] = tool_refs

    if uap_agent.skills:
        annotations["x-uap-skills"] = [_dump(skill) for skill in uap_agent.skills]

    endpoints_payload: List[Dict[str, Any]] = []
    for index, endpoint in enumerate(uap_agent.endpoints):
        payload = _endpoint_payload(
            endpoint, f"endpoints[{index}]", losses
        )
        if payload is not None:
            endpoints_payload.append(payload)
    if endpoints_payload:
        annotations["x-uap-endpoints"] = endpoints_payload

    if uap_agent.auth is not None:
        auth_payload = _auth_payload(uap_agent.auth, "auth", losses)
        if auth_payload is not None:
            annotations["x-uap-auth"] = auth_payload

    annotations["x-uap-capabilities"] = _capabilities_payload(
        uap_agent.capabilities
    )

    compliance_payload, residency_dropped = _compliance_payload(
        uap_agent.compliance
    )
    annotations["x-uap-compliance"] = compliance_payload
    if residency_dropped:
        losses.dropped_fields.append("compliance.data_residency")
        losses.notes.append(
            "MCP does not model compliance.data_residency; field dropped."
        )

    if uap_agent.ui is not None:
        annotations["x-uap-ui"] = _ui_payload(uap_agent.ui)

    if uap_agent.tags:
        annotations["x-uap-tags"] = list(uap_agent.tags)
    if uap_agent.metadata:
        annotations["x-uap-metadata"] = dict(uap_agent.metadata)
    if uap_agent.publisher is not None:
        annotations["x-uap-publisher"] = uap_agent.publisher
    if uap_agent.homepage is not None:
        annotations["x-uap-homepage"] = uap_agent.homepage
    if uap_agent.documentation_url is not None:
        annotations["x-uap-documentation-url"] = uap_agent.documentation_url

    mcp_server: Dict[str, Any] = {
        "name": uap_agent.name,
        "version": uap_agent.version,
        "description": uap_agent.description,
        "tools": mcp_tools,
        "resources": [],
        "prompts": [],
        "annotations": annotations,
    }
    return mcp_server, losses


def to_mcp(obj: Union[Tool, Agent]) -> Tuple[Dict[str, Any], LossInfo]:
    """Dispatch on type and forward to :func:`tool_to_mcp` / :func:`agent_to_mcp`."""
    if isinstance(obj, Tool):
        return tool_to_mcp(obj)
    if isinstance(obj, Agent):
        return agent_to_mcp(obj)
    raise TypeError(
        f"to_mcp expects a UAP Tool or Agent, got {type(obj).__name__}"
    )


def to_mcp_tool(uap_tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Public alias for :func:`tool_to_mcp` (matches the package re-export)."""
    return tool_to_mcp(uap_tool)
