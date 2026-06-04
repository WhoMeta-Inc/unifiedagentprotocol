# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP -> OpenAPI v3 export.

Produces a fully valid OpenAPI 3.0.3 document for a UAP :class:`Agent`
or :class:`Tool`. Enterprise envelope fields are surfaced as ``x-uap-*``
extensions on the relevant operation so the inverse parser can recover
them losslessly.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union

from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    AuthType,
    LossInfo,
    Parameter,
    ParameterLocation,
    Tool,
)


# ---------------------------------------------------------------------------
# Slug helpers (URN-compatible)
# ---------------------------------------------------------------------------

_SLUG_INVALID = re.compile(r"[^a-z0-9._-]+")
_SLUG_DASH = re.compile(r"-{2,}")


def _slugify(raw: str) -> str:
    """Lowercase, replace ``[^a-z0-9._-]`` with ``-``, collapse repeats."""
    lowered = (raw or "").strip().lower()
    slug = _SLUG_INVALID.sub("-", lowered)
    slug = _SLUG_DASH.sub("-", slug)
    slug = slug.strip("-._")
    return slug or "unnamed"


# ---------------------------------------------------------------------------
# JSON-schema helpers
# ---------------------------------------------------------------------------

def _schema_dict(param: Parameter) -> Dict[str, Any]:
    """Serialize a Parameter's schema as a JSON-Schema-style dict."""
    data = param.schema_.model_dump(
        mode="json", exclude_none=True, by_alias=True
    )
    if param.description and "description" not in data:
        data["description"] = param.description
    return data


def _split_parameters(
    params: List[Parameter],
) -> Tuple[List[Parameter], List[Parameter]]:
    """Split parameters into (non-body, body) groups."""
    non_body: List[Parameter] = []
    body: List[Parameter] = []
    for p in params:
        if p.location is ParameterLocation.BODY:
            body.append(p)
        else:
            non_body.append(p)
    return non_body, body


def _openapi_parameters(non_body: List[Parameter]) -> List[Dict[str, Any]]:
    """Build the OpenAPI ``parameters`` list for path/query/header entries."""
    out: List[Dict[str, Any]] = []
    for p in non_body:
        if p.location is ParameterLocation.CONTEXT:
            # Context parameters are runtime-supplied, never exposed to callers.
            continue
        loc = p.location.value
        entry: Dict[str, Any] = {
            "name": p.name,
            "in": loc,
            "required": True if loc == "path" else bool(p.required),
            "schema": _schema_dict(p),
        }
        if p.description and "description" not in entry["schema"]:
            entry["description"] = p.description
        out.append(entry)
    return out


def _body_schema(body_params: List[Parameter]) -> Optional[Dict[str, Any]]:
    """Collapse body params into a single ``object`` JSON Schema."""
    if not body_params:
        return None
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for p in body_params:
        properties[p.name] = _schema_dict(p)
        if p.required:
            required.append(p.name)
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


# ---------------------------------------------------------------------------
# x-uap-* enterprise extensions
# ---------------------------------------------------------------------------

def _x_uap_extensions(tool: Tool) -> Dict[str, Any]:
    """Pack a Tool's UAP-specific fields into ``x-uap-*`` extensions."""
    ext: Dict[str, Any] = {
        "x-uap-urn": tool.id,
        "x-uap-version": tool.version,
        "x-uap-name": tool.name,
    }
    if tool.display_name:
        ext["x-uap-display-name"] = tool.display_name
    # capabilities / compliance always serialize (have defaults) so we
    # round-trip them unconditionally.
    ext["x-uap-capabilities"] = tool.capabilities.model_dump(
        mode="json", exclude_none=True, by_alias=True
    )
    ext["x-uap-compliance"] = tool.compliance.model_dump(
        mode="json", exclude_none=True, by_alias=True
    )
    if tool.cost is not None:
        ext["x-uap-cost"] = tool.cost.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    if tool.triggers:
        ext["x-uap-triggers"] = [
            t.model_dump(mode="json", exclude_none=True, by_alias=True)
            for t in tool.triggers
        ]
    if tool.ui is not None:
        ext["x-uap-ui"] = tool.ui.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    if tool.tags:
        ext["x-uap-tags"] = list(tool.tags)
    if tool.metadata:
        ext["x-uap-metadata"] = dict(tool.metadata)
    if tool.endpoint is not None:
        ext["x-uap-endpoint"] = tool.endpoint.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    if tool.output is not None:
        ext["x-uap-output"] = tool.output.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    # Track parameter locations so the reverse trip restores body vs query/etc.
    locations: Dict[str, str] = {}
    for p in tool.parameters:
        locations[p.name] = p.location.value
    ext["x-uap-param-locations"] = locations
    # Required flags for non-path params (path is always required by OpenAPI).
    required_flags: Dict[str, bool] = {p.name: bool(p.required) for p in tool.parameters}
    ext["x-uap-param-required"] = required_flags
    return ext


def _agent_extensions(agent: Agent) -> Dict[str, Any]:
    """Top-level ``info.x-uap-*`` block for round-tripping agent metadata."""
    ext: Dict[str, Any] = {
        "x-uap-urn": agent.id,
        "x-uap-name": agent.name,
        "x-uap-capabilities": agent.capabilities.model_dump(
            mode="json", exclude_none=True, by_alias=True
        ),
        "x-uap-compliance": agent.compliance.model_dump(
            mode="json", exclude_none=True, by_alias=True
        ),
    }
    if agent.display_name:
        ext["x-uap-display-name"] = agent.display_name
    if agent.skills:
        ext["x-uap-skills"] = [
            s.model_dump(mode="json", exclude_none=True, by_alias=True)
            for s in agent.skills
        ]
    if agent.ui is not None:
        ext["x-uap-ui"] = agent.ui.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    if agent.tags:
        ext["x-uap-tags"] = list(agent.tags)
    if agent.metadata:
        ext["x-uap-metadata"] = dict(agent.metadata)
    if agent.publisher:
        ext["x-uap-publisher"] = agent.publisher
    if agent.homepage:
        ext["x-uap-homepage"] = agent.homepage
    if agent.documentation_url:
        ext["x-uap-documentation-url"] = agent.documentation_url
    return ext


# ---------------------------------------------------------------------------
# Auth mapping -> components.securitySchemes
# ---------------------------------------------------------------------------

def _security_scheme(
    auth: AuthConfig, loss: LossInfo, prefix: str = "auth"
) -> Tuple[Optional[Dict[str, Any]], str]:
    """Return (scheme dict, scheme name) or (None, '') if unmapped."""
    if auth.type == AuthType.NONE:
        return None, ""
    if auth.type == AuthType.API_KEY:
        return (
            {
                "type": "apiKey",
                "in": "header",
                "name": auth.header_name or "X-API-Key",
            },
            "uap_api_key",
        )
    if auth.type == AuthType.BEARER:
        return ({"type": "http", "scheme": "bearer"}, "uap_bearer")
    if auth.type == AuthType.OAUTH2:
        flows: Dict[str, Any] = {}
        token_url = auth.token_url or "https://example.com/token"
        auth_url = auth.authorize_url or "https://example.com/authorize"
        scopes = {s: s for s in auth.scopes} if auth.scopes else {}
        flows["authorizationCode"] = {
            "authorizationUrl": auth_url,
            "tokenUrl": token_url,
            "scopes": scopes,
        }
        return ({"type": "oauth2", "flows": flows}, "uap_oauth2")
    # Unrecognised / unmodeled (mtls, aws_sigv4, gcp_sa) -> http bearer + loss.
    loss.coerced_fields.append(f"{prefix}.type")
    loss.notes.append(
        f"OpenAPI v3 cannot natively express auth.type={auth.type.value!r}; "
        "approximated as 'http bearer'."
    )
    return ({"type": "http", "scheme": "bearer"}, "uap_bearer")


# ---------------------------------------------------------------------------
# Operation builder
# ---------------------------------------------------------------------------

def _operation_for_tool(
    tool: Tool,
    loss: LossInfo,
    security_name: Optional[str],
) -> Dict[str, Any]:
    """Build the OpenAPI operation object for a single Tool."""
    non_body, body = _split_parameters(tool.parameters)
    op: Dict[str, Any] = {
        "operationId": tool.name,
        "summary": tool.display_name or tool.name,
        "description": tool.description,
    }
    op_params = _openapi_parameters(non_body)
    if op_params:
        op["parameters"] = op_params

    body_schema = _body_schema(body)
    if body_schema is not None:
        op["requestBody"] = {
            "required": any(p.required for p in body),
            "content": {"application/json": {"schema": body_schema}},
        }

    # Build a single 200 response.
    response_content: Dict[str, Any]
    if tool.output is not None:
        out_schema = tool.output.schema_.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    else:
        out_schema = {"type": "object"}
    response_content = {"application/json": {"schema": out_schema}}
    op["responses"] = {
        "200": {"description": "Successful invocation.", "content": response_content}
    }

    if tool.tags:
        op["tags"] = list(tool.tags)

    if security_name and tool.auth is None:
        # operation inherits agent security
        pass
    elif tool.auth is not None and tool.auth.type != AuthType.NONE:
        # Per-tool auth — record loss; we still mark it on the operation
        # but at the agent level we used the agent's scheme; per-op auth
        # would need its own securityScheme. Keep simple: drop per-op auth.
        loss.dropped_fields.append("auth")
        loss.notes.append(
            "Per-Tool AuthConfig was not promoted to a dedicated OpenAPI "
            "securityScheme; agent-level auth applies."
        )

    op.update(_x_uap_extensions(tool))
    return op


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def agent_to_openapi(agent: Agent) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Agent` into an OpenAPI 3.0.3 document."""
    loss = LossInfo()

    info: Dict[str, Any] = {
        "title": agent.display_name or agent.name,
        "version": agent.version,
        "description": agent.description,
    }
    info.update(_agent_extensions(agent))

    servers: List[Dict[str, Any]] = []
    for idx, ep in enumerate(agent.endpoints):
        if ep.url:
            entry: Dict[str, Any] = {"url": ep.url}
            extras: Dict[str, Any] = ep.model_dump(
                mode="json", exclude_none=True, by_alias=True
            )
            extras.pop("url", None)
            if extras:
                entry["x-uap-endpoint"] = extras
            servers.append(entry)
        else:
            loss.dropped_fields.append(f"endpoints[{idx}].url")
            loss.notes.append(
                f"endpoints[{idx}] has no URL; cannot map to OpenAPI server."
            )

    components: Dict[str, Any] = {}
    security_requirements: List[Dict[str, List[str]]] = []
    if agent.auth is not None:
        scheme, name = _security_scheme(agent.auth, loss, prefix="auth")
        if scheme is not None:
            components.setdefault("securitySchemes", {})[name] = scheme
            scope_names = (
                list(agent.auth.scopes) if agent.auth.type == AuthType.OAUTH2 else []
            )
            security_requirements.append({name: scope_names})
            # Smuggle the secret_ref so from_openapi can reconstruct.
            if agent.auth.secret_ref:
                scheme["x-uap-secret-ref"] = agent.auth.secret_ref
            scheme["x-uap-auth-type"] = agent.auth.type.value
            if agent.auth.header_name:
                scheme["x-uap-header-name"] = agent.auth.header_name
            if agent.auth.token_url:
                scheme["x-uap-token-url"] = agent.auth.token_url
            if agent.auth.authorize_url:
                scheme["x-uap-authorize-url"] = agent.auth.authorize_url
            if agent.auth.audience:
                scheme["x-uap-audience"] = agent.auth.audience

    paths: Dict[str, Any] = {}
    security_name = (
        next(iter(components.get("securitySchemes", {}).keys()), None)
        if "securitySchemes" in components
        else None
    )

    inline_tools = [t for t in agent.tools if isinstance(t, Tool)]
    urn_refs = [t for t in agent.tools if isinstance(t, str)]
    if urn_refs:
        loss.dropped_fields.append("tools[urn_refs]")
        loss.notes.append(
            "OpenAPI v3 has no representation for bare Tool URN references; "
            "preserved under info.x-uap-tool-refs."
        )
        info["x-uap-tool-refs"] = urn_refs

    seen_paths: Dict[str, int] = {}
    for tool in inline_tools:
        slug = _slugify(tool.name)
        # Build the path. If a tool defines path parameters, embed them.
        path_params = [p for p in tool.parameters if p.location is ParameterLocation.PATH]
        path = f"/tools/{slug}"
        for p in path_params:
            path += f"/{{{p.name}}}"
        # Deduplicate identical paths.
        if path in seen_paths:
            seen_paths[path] += 1
            path = f"{path}-{seen_paths[path]}"
        else:
            seen_paths[path] = 0

        operation = _operation_for_tool(tool, loss, security_name)
        paths[path] = {"post": operation}

    spec: Dict[str, Any] = {
        "openapi": "3.0.3",
        "info": info,
        "paths": paths,
    }
    if servers:
        spec["servers"] = servers
    if components:
        spec["components"] = components
    if security_requirements:
        spec["security"] = security_requirements

    return spec, loss


def tool_to_openapi(tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Wrap a standalone :class:`Tool` in a synthetic Agent and emit OpenAPI."""
    synthetic = Agent(
        id=f"urn:uap:agent:{_slugify(tool.name)}",
        name=tool.name,
        display_name=tool.display_name,
        description=tool.description,
        version=tool.version,
        tools=[tool],
        auth=tool.auth,
        endpoints=[tool.endpoint] if tool.endpoint is not None else [],
    )
    return agent_to_openapi(synthetic)


def to_openapi(obj: Union[Agent, Tool]) -> Tuple[Dict[str, Any], LossInfo]:
    """Public dispatcher. ``Agent`` -> full doc, ``Tool`` -> single-tool doc."""
    if isinstance(obj, Agent):
        return agent_to_openapi(obj)
    if isinstance(obj, Tool):
        return tool_to_openapi(obj)
    raise TypeError(
        f"to_openapi expects Agent or Tool; got {type(obj).__name__}"
    )
