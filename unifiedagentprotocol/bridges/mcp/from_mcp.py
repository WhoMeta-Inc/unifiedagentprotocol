# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Convert MCP descriptors into UAP :class:`Tool` / :class:`Agent` objects.

Mapping rules (inverse of :mod:`unifiedagentprotocol.bridges.mcp.to_mcp`)
------------------------------------------------------------------------

MCP Tool ``{"name", "description", "inputSchema", "annotations"}``::

    - ``name``                          -> ``Tool.name``
    - ``description``                   -> ``Tool.description``
    - ``inputSchema.properties[<n>]``   -> ``Tool.parameters[<n>].schema``
    - ``inputSchema.required[]``        -> ``Tool.parameters[*].required``
    - ``annotations.title``             -> ``Tool.display_name``
    - ``annotations.x-uap-id``          -> ``Tool.id`` (or synthesised URN)
    - ``annotations.x-uap-version``     -> ``Tool.version``
    - ``annotations.x-uap-parameters``  -> ``Tool.parameters[*]`` overrides
                                          (``location``, ``description``)
    - ``annotations.x-uap-output``      -> ``Tool.output``
    - ``annotations.x-uap-endpoint``    -> ``Tool.endpoint``
    - ``annotations.x-uap-auth``        -> ``Tool.auth``
    - ``annotations.x-uap-capabilities``-> ``Tool.capabilities``
    - ``annotations.x-uap-compliance``  -> ``Tool.compliance``
                                          (``data_residency`` is never present)
    - ``annotations.x-uap-cost``        -> ``Tool.cost``
    - ``annotations.x-uap-ui``          -> ``Tool.ui``
    - ``annotations.x-uap-tags``        -> ``Tool.tags``
    - ``annotations.x-uap-metadata``    -> ``Tool.metadata``

MCP server descriptor ``{"name", "version", "description", "tools", ...}``::

    - ``name``                          -> ``Agent.name``
    - ``version``                       -> ``Agent.version``
    - ``description``                   -> ``Agent.description``
    - each entry of ``tools[]``         -> ``Agent.tools[]`` (Tool)
    - ``annotations.x-uap-tool-refs[]`` -> ``Agent.tools[]`` (URN string)
    - ``annotations.title``             -> ``Agent.display_name``
    - ``annotations.x-uap-id``          -> ``Agent.id`` (or synthesised URN)
    - ``annotations.x-uap-skills``      -> ``Agent.skills``
    - ``annotations.x-uap-endpoints``   -> ``Agent.endpoints``
    - ``annotations.x-uap-auth``        -> ``Agent.auth``
    - ``annotations.x-uap-capabilities``-> ``Agent.capabilities``
    - ``annotations.x-uap-compliance``  -> ``Agent.compliance``
    - ``annotations.x-uap-ui``          -> ``Agent.ui``
    - ``annotations.x-uap-tags``        -> ``Agent.tags``
    - ``annotations.x-uap-metadata``    -> ``Agent.metadata``
    - ``annotations.x-uap-publisher``   -> ``Agent.publisher``
    - ``annotations.x-uap-homepage``    -> ``Agent.homepage``
    - ``annotations.x-uap-documentation-url`` -> ``Agent.documentation_url``

Whenever the MCP payload omits ``annotations.x-uap-id`` (i.e. it was not
produced by UAP), the URN is synthesised from the ``name``.
"""
from __future__ import annotations

import re
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
    ParameterSchema,
    Skill,
    Tool,
    UIConfig,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _slugify(value: str) -> str:
    """Coerce ``value`` into a URN-safe slug.

    The result is guaranteed to satisfy the regex
    ``[a-z0-9][a-z0-9._-]*`` enforced by :func:`validate_urn`. When the
    input cannot be slugified at all, a safe fallback is returned.
    """
    if not value:
        return "unnamed"
    lowered = value.strip().lower()
    cleaned = _SLUG_RE.sub("-", lowered).strip("-._")
    if not cleaned:
        return "unnamed"
    if not (cleaned[0].isalnum()):
        cleaned = f"x-{cleaned}"
    return cleaned


def _synth_urn(kind: str, name: str) -> str:
    """Build ``urn:uap:<kind>:<slug>`` from a bare name."""
    return f"urn:uap:{kind}:{_slugify(name)}"


def _parameter_from_json_schema(
    name: str,
    schema_obj: Dict[str, Any],
    required: bool,
    location: ParameterLocation,
    description: Any,
) -> Parameter:
    """Build a Parameter from a JSON-Schema fragment.

    ``description`` is sourced from the explicit UAP override if present;
    otherwise we fall back to ``schema_obj.description``.
    """
    parameter_schema = ParameterSchema.model_validate(schema_obj)
    kwargs: Dict[str, Any] = {
        "name": name,
        "schema": parameter_schema,
        "required": required,
        "location": location,
    }
    if isinstance(description, str):
        kwargs["description"] = description
    return Parameter(**kwargs)


def _decode_parameters(
    input_schema: Dict[str, Any],
    uap_parameter_meta: List[Dict[str, Any]] | None,
) -> Tuple[List[Parameter], LossInfo]:
    """Reverse :func:`to_mcp._build_input_schema`.

    The UAP parameter list is rebuilt in the order declared by
    ``uap_parameter_meta`` when that override is provided (this preserves
    the original ordering across round-trips). Otherwise we fall back to
    the order of ``inputSchema.properties``.
    """
    losses = LossInfo()
    properties: Dict[str, Any] = input_schema.get("properties", {}) or {}
    required_list: List[str] = list(input_schema.get("required") or [])
    required_set = set(required_list)

    overrides_by_name: Dict[str, Dict[str, Any]] = {}
    ordered_names: List[str] = []
    if uap_parameter_meta:
        for entry in uap_parameter_meta:
            if not isinstance(entry, dict):
                continue
            entry_name = entry.get("name")
            if not isinstance(entry_name, str):
                continue
            overrides_by_name[entry_name] = entry
            ordered_names.append(entry_name)

    # Append properties not covered by the overrides (e.g. new fields
    # added by an MCP producer that doesn't know about UAP).
    for prop_name in properties:
        if prop_name not in overrides_by_name:
            ordered_names.append(prop_name)

    parameters: List[Parameter] = []
    for prop_name in ordered_names:
        schema_obj = properties.get(prop_name)
        override = overrides_by_name.get(prop_name, {})

        if schema_obj is None and "schema" in override:
            schema_obj = override["schema"]
        if not isinstance(schema_obj, dict):
            schema_obj = {}

        required_flag = override.get("required")
        if not isinstance(required_flag, bool):
            required_flag = prop_name in required_set

        location_raw = override.get("location", ParameterLocation.BODY.value)
        try:
            location = ParameterLocation(location_raw)
        except ValueError:
            losses.coerced_fields.append(f"parameters.{prop_name}.location")
            location = ParameterLocation.BODY

        description = override.get("description")
        parameters.append(
            _parameter_from_json_schema(
                prop_name,
                schema_obj,
                required_flag,
                location,
                description,
            )
        )

    return parameters, losses


def _get_annotations(mcp_obj: Dict[str, Any]) -> Dict[str, Any]:
    annotations = mcp_obj.get("annotations") or {}
    if not isinstance(annotations, dict):
        return {}
    return annotations


def _decode_capabilities(payload: Any) -> Capabilities:
    if not isinstance(payload, dict):
        return Capabilities()
    return Capabilities.model_validate(payload)


def _decode_compliance(payload: Any) -> Compliance:
    if not isinstance(payload, dict):
        return Compliance()
    return Compliance.model_validate(payload)


def _decode_cost(payload: Any) -> CostHint | None:
    if not isinstance(payload, dict):
        return None
    return CostHint.model_validate(payload)


def _decode_ui(payload: Any) -> UIConfig | None:
    if not isinstance(payload, dict):
        return None
    return UIConfig.model_validate(payload)


def _decode_endpoint(payload: Any) -> Endpoint | None:
    if not isinstance(payload, dict):
        return None
    return Endpoint.model_validate(payload)


def _decode_auth(payload: Any) -> AuthConfig | None:
    if not isinstance(payload, dict):
        return None
    return AuthConfig.model_validate(payload)


def _decode_output(payload: Any) -> Dict[str, Any] | None:
    """Return the raw dict so :class:`Tool` can validate it.

    Avoids importing the private :class:`OutputSchema` class directly while
    still letting Pydantic build the nested model when ``Tool`` is
    constructed.
    """
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def _decode_skills(payload: Any) -> List[Skill]:
    if not isinstance(payload, list):
        return []
    skills: List[Skill] = []
    for item in payload:
        if isinstance(item, dict):
            skills.append(Skill.model_validate(item))
    return skills


def _decode_endpoints(payload: Any) -> List[Endpoint]:
    if not isinstance(payload, list):
        return []
    endpoints: List[Endpoint] = []
    for item in payload:
        endpoint = _decode_endpoint(item)
        if endpoint is not None:
            endpoints.append(endpoint)
    return endpoints


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def tool_from_mcp(mcp_tool: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Build a UAP :class:`Tool` from an MCP Tool object."""
    if not isinstance(mcp_tool, dict):
        raise TypeError("mcp_tool must be a dict")

    losses = LossInfo()
    annotations = _get_annotations(mcp_tool)

    name = mcp_tool.get("name") or "unnamed_tool"
    description = mcp_tool.get("description") or ""
    input_schema = mcp_tool.get("inputSchema") or {"type": "object", "properties": {}}

    parameters, param_losses = _decode_parameters(
        input_schema,
        annotations.get("x-uap-parameters"),
    )
    losses = losses.merge(param_losses)

    urn = annotations.get("x-uap-id") or _synth_urn("tool", name)
    version = annotations.get("x-uap-version") or "0.1.0"
    display_name = annotations.get("title")

    capabilities = _decode_capabilities(annotations.get("x-uap-capabilities"))
    compliance = _decode_compliance(annotations.get("x-uap-compliance"))
    cost = _decode_cost(annotations.get("x-uap-cost"))
    ui = _decode_ui(annotations.get("x-uap-ui"))
    endpoint = _decode_endpoint(annotations.get("x-uap-endpoint"))
    auth = _decode_auth(annotations.get("x-uap-auth"))
    output = _decode_output(annotations.get("x-uap-output"))

    tags_raw = annotations.get("x-uap-tags") or []
    tags: List[str] = [t for t in tags_raw if isinstance(t, str)]

    metadata_raw = annotations.get("x-uap-metadata") or {}
    metadata: Dict[str, Any] = (
        dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    )

    tool_kwargs: Dict[str, Any] = {
        "id": urn,
        "name": name,
        "description": description,
        "version": version,
        "parameters": parameters,
        "capabilities": capabilities,
        "compliance": compliance,
        "tags": tags,
        "metadata": metadata,
    }
    if display_name is not None:
        tool_kwargs["display_name"] = display_name
    if output is not None:
        tool_kwargs["output"] = output
    if endpoint is not None:
        tool_kwargs["endpoint"] = endpoint
    if auth is not None:
        tool_kwargs["auth"] = auth
    if cost is not None:
        tool_kwargs["cost"] = cost
    if ui is not None:
        tool_kwargs["ui"] = ui

    tool = Tool(**tool_kwargs)
    return tool, losses


def agent_from_mcp(mcp_server: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Build a UAP :class:`Agent` from an MCP server descriptor."""
    if not isinstance(mcp_server, dict):
        raise TypeError("mcp_server must be a dict")

    losses = LossInfo()
    annotations = _get_annotations(mcp_server)

    name = mcp_server.get("name") or "unnamed_agent"
    description = mcp_server.get("description") or ""
    version = mcp_server.get("version") or annotations.get("x-uap-version") or "0.1.0"

    raw_tools = mcp_server.get("tools") or []
    tools: List[Union[Tool, str]] = []
    for index, raw in enumerate(raw_tools):
        if isinstance(raw, dict):
            tool, tool_losses = tool_from_mcp(raw)
            tools.append(tool)
            for field in tool_losses.dropped_fields:
                losses.dropped_fields.append(f"tools[{index}].{field}")
            for field in tool_losses.coerced_fields:
                losses.coerced_fields.append(f"tools[{index}].{field}")
            losses.notes.extend(tool_losses.notes)

    tool_refs = annotations.get("x-uap-tool-refs") or []
    if isinstance(tool_refs, list):
        for ref in tool_refs:
            if isinstance(ref, str):
                tools.append(ref)

    urn = annotations.get("x-uap-id") or _synth_urn("agent", name)
    display_name = annotations.get("title")

    skills = _decode_skills(annotations.get("x-uap-skills"))
    endpoints = _decode_endpoints(annotations.get("x-uap-endpoints"))
    auth = _decode_auth(annotations.get("x-uap-auth"))
    capabilities = _decode_capabilities(annotations.get("x-uap-capabilities"))
    compliance = _decode_compliance(annotations.get("x-uap-compliance"))
    ui = _decode_ui(annotations.get("x-uap-ui"))

    tags_raw = annotations.get("x-uap-tags") or []
    tags: List[str] = [t for t in tags_raw if isinstance(t, str)]

    metadata_raw = annotations.get("x-uap-metadata") or {}
    metadata: Dict[str, Any] = (
        dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    )

    publisher = annotations.get("x-uap-publisher")
    homepage = annotations.get("x-uap-homepage")
    documentation_url = annotations.get("x-uap-documentation-url")

    agent_kwargs: Dict[str, Any] = {
        "id": urn,
        "name": name,
        "description": description,
        "version": version,
        "tools": tools,
        "skills": skills,
        "endpoints": endpoints,
        "capabilities": capabilities,
        "compliance": compliance,
        "tags": tags,
        "metadata": metadata,
    }
    if display_name is not None:
        agent_kwargs["display_name"] = display_name
    if auth is not None:
        agent_kwargs["auth"] = auth
    if ui is not None:
        agent_kwargs["ui"] = ui
    if isinstance(publisher, str):
        agent_kwargs["publisher"] = publisher
    if isinstance(homepage, str):
        agent_kwargs["homepage"] = homepage
    if isinstance(documentation_url, str):
        agent_kwargs["documentation_url"] = documentation_url

    agent = Agent(**agent_kwargs)
    return agent, losses


def from_mcp(obj: Dict[str, Any]) -> Tuple[Union[Tool, Agent], LossInfo]:
    """Auto-detect Tool vs server descriptor and delegate.

    Detection rule: a payload with an ``inputSchema`` is a Tool; a payload
    with a ``tools`` array is a server descriptor. When both heuristics
    apply, ``inputSchema`` wins (a single Tool can carry an embedded
    ``tools`` field via annotations, but never the other way around).
    """
    if not isinstance(obj, dict):
        raise TypeError("from_mcp expects a dict")

    if "inputSchema" in obj:
        return tool_from_mcp(obj)
    if "tools" in obj:
        return agent_from_mcp(obj)
    raise ValueError(
        "Cannot detect MCP object kind: expected 'inputSchema' (Tool) "
        "or 'tools' (server descriptor)."
    )


def from_mcp_tool(mcp_tool: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Public alias for :func:`tool_from_mcp` (matches the package re-export)."""
    return tool_from_mcp(mcp_tool)
