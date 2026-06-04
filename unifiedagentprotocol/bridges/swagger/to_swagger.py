# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP -> Swagger v2.0 export.

Swagger 2.0 is a strict subset of the modeling power of OpenAPI v3 and
UAP. In particular, it cannot express mTLS or AWS SigV4 auth, has only a
single ``host`` / ``basePath`` pair (so multiple endpoints downgrade to
the first), and its OAuth2 scheme is split across flow-specific
fields rather than the v3 ``flows`` object.

Lossy aspects are recorded in :class:`LossInfo`.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

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
# Slug
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
# Parameter mapping
# ---------------------------------------------------------------------------

def _schema_dict(param: Parameter) -> Dict[str, Any]:
    data = param.schema_.model_dump(mode="json", exclude_none=True, by_alias=True)
    if param.description and "description" not in data:
        data["description"] = param.description
    return data


def _split_parameters(
    params: List[Parameter],
) -> Tuple[List[Parameter], List[Parameter]]:
    non_body: List[Parameter] = []
    body: List[Parameter] = []
    for p in params:
        if p.location is ParameterLocation.BODY:
            body.append(p)
        elif p.location is ParameterLocation.CONTEXT:
            continue
        else:
            non_body.append(p)
    return non_body, body


def _swagger_parameters(
    non_body: List[Parameter], body: List[Parameter]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in non_body:
        loc = p.location.value
        schema = _schema_dict(p)
        # Swagger v2 inlines the primitive's "type" rather than using "schema".
        entry: Dict[str, Any] = {
            "name": p.name,
            "in": loc,
            "required": True if loc == "path" else bool(p.required),
        }
        if isinstance(schema.get("type"), str):
            entry["type"] = schema["type"]
        for k in ("format", "enum", "default", "minimum", "maximum", "minLength", "maxLength", "pattern", "description", "items"):
            if k in schema:
                entry[k] = schema[k]
        out.append(entry)
    if body:
        body_schema: Dict[str, Any] = {"type": "object", "properties": {}}
        required: List[str] = []
        for p in body:
            body_schema["properties"][p.name] = _schema_dict(p)
            if p.required:
                required.append(p.name)
        if required:
            body_schema["required"] = required
        out.append(
            {
                "name": "body",
                "in": "body",
                "required": any(p.required for p in body),
                "schema": body_schema,
            }
        )
    return out


# ---------------------------------------------------------------------------
# x-uap-* extensions (same shape as openapi)
# ---------------------------------------------------------------------------

def _x_uap_extensions(tool: Tool) -> Dict[str, Any]:
    ext: Dict[str, Any] = {
        "x-uap-urn": tool.id,
        "x-uap-version": tool.version,
        "x-uap-name": tool.name,
    }
    if tool.display_name:
        ext["x-uap-display-name"] = tool.display_name
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
    locations: Dict[str, str] = {p.name: p.location.value for p in tool.parameters}
    ext["x-uap-param-locations"] = locations
    required_flags: Dict[str, bool] = {
        p.name: bool(p.required) for p in tool.parameters
    }
    ext["x-uap-param-required"] = required_flags
    return ext


def _agent_extensions(agent: Agent) -> Dict[str, Any]:
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
# Auth mapping -> securityDefinitions
# ---------------------------------------------------------------------------

def _security_scheme(
    auth: AuthConfig, loss: LossInfo, prefix: str = "auth"
) -> Tuple[Optional[Dict[str, Any]], str]:
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
        # Swagger v2 has no http-bearer — fall back to apiKey 'Authorization'.
        loss.coerced_fields.append(f"{prefix}.type")
        loss.notes.append(
            "Swagger 2.0 has no native bearer scheme; approximated as "
            "apiKey in header 'Authorization'."
        )
        return (
            {
                "type": "apiKey",
                "in": "header",
                "name": auth.header_name or "Authorization",
            },
            "uap_bearer",
        )
    if auth.type == AuthType.OAUTH2:
        # Pick authorizationCode → 'accessCode' flow in v2 terminology.
        scheme: Dict[str, Any] = {
            "type": "oauth2",
            "flow": "accessCode",
            "authorizationUrl": auth.authorize_url or "https://example.com/authorize",
            "tokenUrl": auth.token_url or "https://example.com/token",
            "scopes": {s: s for s in auth.scopes} if auth.scopes else {},
        }
        return scheme, "uap_oauth2"
    # mTLS / AWS SigV4 / GCP service account — downgrade with explicit note.
    loss.coerced_fields.append(f"{prefix}.type")
    loss.notes.append(
        f"Swagger 2.0 cannot express auth.type={auth.type.value!r}; "
        "downgraded to apiKey in 'Authorization' header."
    )
    return (
        {
            "type": "apiKey",
            "in": "header",
            "name": auth.header_name or "Authorization",
        },
        "uap_bearer",
    )


# ---------------------------------------------------------------------------
# Operation builder
# ---------------------------------------------------------------------------

def _operation_for_tool(tool: Tool, loss: LossInfo) -> Dict[str, Any]:
    non_body, body = _split_parameters(tool.parameters)
    op: Dict[str, Any] = {
        "operationId": tool.name,
        "summary": tool.display_name or tool.name,
        "description": tool.description,
    }
    swagger_params = _swagger_parameters(non_body, body)
    if swagger_params:
        op["parameters"] = swagger_params

    if tool.output is not None:
        out_schema = tool.output.schema_.model_dump(
            mode="json", exclude_none=True, by_alias=True
        )
    else:
        out_schema = {"type": "object"}
    op["responses"] = {
        "200": {"description": "Successful invocation.", "schema": out_schema}
    }

    if tool.tags:
        op["tags"] = list(tool.tags)

    if tool.auth is not None and tool.auth.type != AuthType.NONE:
        loss.dropped_fields.append("auth")
        loss.notes.append(
            "Per-Tool AuthConfig was not promoted to a dedicated Swagger 2.0 "
            "security definition; top-level auth applies."
        )

    op.update(_x_uap_extensions(tool))
    return op


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def _split_host(url: str) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Split a full URL into Swagger 2 (host, basePath, schemes)."""
    try:
        parsed = urlparse(url)
    except Exception:  # pragma: no cover — defensive
        return None, None, ["https"]
    if not parsed.netloc:
        return None, None, ["https"]
    schemes = [parsed.scheme] if parsed.scheme else ["https"]
    base = parsed.path or ""
    return parsed.netloc, base or None, schemes


def agent_to_swagger(agent: Agent) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Agent` into a Swagger 2.0 dict."""
    loss = LossInfo()

    info: Dict[str, Any] = {
        "title": agent.display_name or agent.name,
        "version": agent.version,
        "description": agent.description,
    }
    info.update(_agent_extensions(agent))

    spec: Dict[str, Any] = {
        "swagger": "2.0",
        "info": info,
        "paths": {},
    }

    # Server / host / basePath / schemes.
    if agent.endpoints:
        first = agent.endpoints[0]
        if first.url:
            host, base, schemes = _split_host(first.url)
            if host:
                spec["host"] = host
            if base:
                spec["basePath"] = base
            spec["schemes"] = schemes
        if len(agent.endpoints) > 1:
            loss.dropped_fields.append("endpoints[1:]")
            loss.notes.append(
                "Swagger 2.0 has a single host/basePath; only endpoints[0] was kept."
            )

    # securityDefinitions + security.
    if agent.auth is not None:
        scheme, name = _security_scheme(agent.auth, loss)
        if scheme is not None:
            spec.setdefault("securityDefinitions", {})[name] = scheme
            scope_list = (
                list(agent.auth.scopes) if agent.auth.type == AuthType.OAUTH2 else []
            )
            spec["security"] = [{name: scope_list}]
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

    # Tools.
    inline_tools = [t for t in agent.tools if isinstance(t, Tool)]
    urn_refs = [t for t in agent.tools if isinstance(t, str)]
    if urn_refs:
        info["x-uap-tool-refs"] = urn_refs
        loss.dropped_fields.append("tools[urn_refs]")
        loss.notes.append(
            "Swagger 2.0 has no representation for bare Tool URN references; "
            "preserved under info.x-uap-tool-refs."
        )

    seen_paths: Dict[str, int] = {}
    for tool in inline_tools:
        slug = _slugify(tool.name)
        path_params = [
            p for p in tool.parameters if p.location is ParameterLocation.PATH
        ]
        path = f"/tools/{slug}"
        for p in path_params:
            path += f"/{{{p.name}}}"
        if path in seen_paths:
            seen_paths[path] += 1
            path = f"{path}-{seen_paths[path]}"
        else:
            seen_paths[path] = 0

        spec["paths"][path] = {"post": _operation_for_tool(tool, loss)}

    return spec, loss


def to_swagger(obj: Union[Agent, Tool]) -> Tuple[Dict[str, Any], LossInfo]:
    """Public dispatcher. ``Agent`` -> full Swagger doc, ``Tool`` -> wrapped."""
    if isinstance(obj, Agent):
        return agent_to_swagger(obj)
    if isinstance(obj, Tool):
        synthetic = Agent(
            id=f"urn:uap:agent:{_slugify(obj.name)}",
            name=obj.name,
            display_name=obj.display_name,
            description=obj.description,
            version=obj.version,
            tools=[obj],
            auth=obj.auth,
            endpoints=[obj.endpoint] if obj.endpoint is not None else [],
        )
        return agent_to_swagger(synthetic)
    raise TypeError(
        f"to_swagger expects Agent or Tool; got {type(obj).__name__}"
    )
