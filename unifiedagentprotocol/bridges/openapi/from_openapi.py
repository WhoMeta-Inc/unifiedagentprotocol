# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""OpenAPI v3 -> UAP import.

Parses an OpenAPI 3.x document into a UAP :class:`Agent` containing one
:class:`Tool` per operation. UAP-specific metadata smuggled through
``x-uap-*`` extensions by :mod:`to_openapi` is recovered to make the
round-trip lossless for the enterprise envelope.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    AuthType,
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
    Trigger,
    Transport,
    UIConfig,
)
from unifiedagentprotocol.core.schema.tool import OutputSchema


# ---------------------------------------------------------------------------
# Slug helpers (mirror to_openapi)
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
# JSON-Schema -> ParameterSchema
# ---------------------------------------------------------------------------

# Fields that map 1:1 from a JSON Schema dict to ``ParameterSchema`` via
# aliases. Anything outside this set is ignored at construction time but
# Pydantic's ``extra="allow"`` preserves it.
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
    """Convert a raw JSON-Schema dict into a :class:`ParameterSchema`."""
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
                # Keep raw schemas; ParameterSchema knows how to nest.
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


# ---------------------------------------------------------------------------
# Operation -> Tool
# ---------------------------------------------------------------------------

def _parameter_from_operation_entry(
    entry: Dict[str, Any], loss: LossInfo, idx: int
) -> Optional[Parameter]:
    """Translate one ``parameters[i]`` entry (path/query/header)."""
    name = entry.get("name")
    where = entry.get("in")
    if not name or not where:
        loss.dropped_fields.append(f"parameters[{idx}]")
        return None
    if where not in {"path", "query", "header"}:
        loss.dropped_fields.append(f"parameters[{idx}].in={where!r}")
        loss.notes.append(
            f"OpenAPI parameter location {where!r} is not modelled by UAP; dropped."
        )
        return None
    schema = entry.get("schema") or {"type": "string"}
    p_schema = _to_parameter_schema(schema)
    return Parameter(
        name=name,
        schema=p_schema,
        required=bool(entry.get("required", where == "path")),
        location=ParameterLocation(where),
        description=entry.get("description"),
    )


def _parameters_from_body(
    body_schema: Dict[str, Any], loss: LossInfo
) -> List[Parameter]:
    """Decompose an ``object`` request-body schema into UAP body Parameters."""
    out: List[Parameter] = []
    if not isinstance(body_schema, dict):
        return out
    props = body_schema.get("properties") or {}
    required = set(body_schema.get("required") or [])
    if not isinstance(props, dict):
        return out
    for name, raw in props.items():
        if not isinstance(raw, dict):
            loss.dropped_fields.append(f"requestBody.properties.{name}")
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


def _restore_capabilities(raw: Any, loss: LossInfo) -> Capabilities:
    if isinstance(raw, dict):
        try:
            return Capabilities(**raw)
        except Exception as exc:  # pragma: no cover — defensive
            loss.notes.append(f"x-uap-capabilities malformed: {exc!r}; defaulted.")
    return Capabilities()


def _restore_compliance(raw: Any, loss: LossInfo) -> Compliance:
    if isinstance(raw, dict):
        try:
            return Compliance(**raw)
        except Exception as exc:  # pragma: no cover — defensive
            loss.notes.append(f"x-uap-compliance malformed: {exc!r}; defaulted.")
    return Compliance()


def _restore_cost(raw: Any) -> Optional[CostHint]:
    if isinstance(raw, dict):
        try:
            return CostHint(**raw)
        except Exception:  # pragma: no cover — defensive
            return None
    return None


def _restore_triggers(raw: Any) -> List[Trigger]:
    out: List[Trigger] = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                try:
                    out.append(Trigger(**entry))
                except Exception:  # pragma: no cover — defensive
                    continue
    return out


def _restore_ui(raw: Any) -> Optional[UIConfig]:
    if isinstance(raw, dict):
        try:
            return UIConfig(**raw)
        except Exception:  # pragma: no cover — defensive
            return None
    return None


def _restore_endpoint(raw: Any) -> Optional[Endpoint]:
    if isinstance(raw, dict):
        try:
            return Endpoint(**raw)
        except Exception:  # pragma: no cover — defensive
            return None
    return None


def _restore_output(raw: Any) -> Optional[OutputSchema]:
    if isinstance(raw, dict):
        try:
            return OutputSchema(**raw)
        except Exception:  # pragma: no cover — defensive
            return None
    return None


def _tool_from_operation(
    path: str,
    method: str,
    op: Dict[str, Any],
    loss: LossInfo,
) -> Tool:
    """Build a Tool from a single OpenAPI operation object."""
    locations: Dict[str, str] = op.get("x-uap-param-locations") or {}
    required_flags: Dict[str, bool] = op.get("x-uap-param-required") or {}

    params: List[Parameter] = []
    # 1) parameters list (path / query / header)
    for idx, entry in enumerate(op.get("parameters") or []):
        if not isinstance(entry, dict):
            loss.dropped_fields.append(f"parameters[{idx}]")
            continue
        p = _parameter_from_operation_entry(entry, loss, idx)
        if p is not None:
            params.append(p)

    # 2) requestBody.application/json -> body params
    rb = op.get("requestBody") or {}
    if isinstance(rb, dict):
        content = rb.get("content") or {}
        if isinstance(content, dict):
            app_json = content.get("application/json") or {}
            body_schema = app_json.get("schema") if isinstance(app_json, dict) else None
            if isinstance(body_schema, dict):
                params.extend(_parameters_from_body(body_schema, loss))

    # 3) Apply x-uap-param-locations to restore original locations.
    for p in params:
        loc = locations.get(p.name)
        if loc and loc != p.location.value:
            try:
                p.location = ParameterLocation(loc)
            except ValueError:
                loss.coerced_fields.append(f"parameters[{p.name}].location")
        if p.name in required_flags:
            p.required = bool(required_flags[p.name])

    # 4) Output schema
    response_schema: Optional[Dict[str, Any]] = None
    responses = op.get("responses") or {}
    if isinstance(responses, dict):
        ok = responses.get("200") or responses.get(200)
        if isinstance(ok, dict):
            content = ok.get("content") or {}
            if isinstance(content, dict):
                app_json = content.get("application/json") or {}
                if isinstance(app_json, dict):
                    response_schema = app_json.get("schema")
    output: Optional[OutputSchema] = None
    explicit_output = _restore_output(op.get("x-uap-output"))
    if explicit_output is not None:
        output = explicit_output
    elif isinstance(response_schema, dict):
        output = OutputSchema(schema=_to_parameter_schema(response_schema))

    # 5) Identity & metadata
    urn = op.get("x-uap-urn")
    if isinstance(urn, str) and urn.startswith("urn:uap:tool:"):
        tool_id = urn
    else:
        op_id = op.get("operationId") or f"{method}_{path}"
        tool_id = f"urn:uap:tool:{_slugify(op_id)}"
        loss.notes.append(
            f"Operation {method.upper()} {path} did not carry x-uap-urn; "
            f"synthesized tool URN {tool_id!r}."
        )

    name_raw = op.get("x-uap-name") or op.get("operationId") or f"{method}_{path}"
    name_safe = re.sub(r"[^A-Za-z0-9_]+", "_", str(name_raw)).strip("_") or "tool"
    if name_safe[0].isdigit():
        name_safe = f"t_{name_safe}"

    description = op.get("description") or op.get("summary") or ""
    version = str(op.get("x-uap-version") or "0.1.0")
    display_name = op.get("x-uap-display-name") or op.get("summary")

    capabilities = _restore_capabilities(op.get("x-uap-capabilities"), loss)
    compliance = _restore_compliance(op.get("x-uap-compliance"), loss)
    cost = _restore_cost(op.get("x-uap-cost"))
    triggers = _restore_triggers(op.get("x-uap-triggers"))
    ui = _restore_ui(op.get("x-uap-ui"))
    endpoint = _restore_endpoint(op.get("x-uap-endpoint"))
    metadata_raw = op.get("x-uap-metadata") or {}
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    tags_ext = op.get("x-uap-tags")
    if isinstance(tags_ext, list):
        tags = [str(t) for t in tags_ext]
    else:
        tags = [str(t) for t in (op.get("tags") or [])]

    return Tool(
        id=tool_id,
        name=name_safe,
        display_name=display_name,
        description=str(description),
        version=version,
        parameters=params,
        output=output,
        endpoint=endpoint,
        triggers=triggers,
        capabilities=capabilities,
        compliance=compliance,
        cost=cost,
        ui=ui,
        tags=tags,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Auth recovery
# ---------------------------------------------------------------------------

def _restore_auth(
    components: Dict[str, Any], loss: LossInfo
) -> Optional[AuthConfig]:
    schemes = (components or {}).get("securitySchemes") or {}
    if not isinstance(schemes, dict) or not schemes:
        return None
    # Prefer the first registered scheme.
    first_name, scheme = next(iter(schemes.items()))
    if not isinstance(scheme, dict):
        return None
    declared_type = scheme.get("x-uap-auth-type")
    if isinstance(declared_type, str):
        try:
            auth_type = AuthType(declared_type)
        except ValueError:
            auth_type = AuthType.BEARER
            loss.coerced_fields.append("auth.type")
    else:
        # Map by OpenAPI shape.
        t = scheme.get("type")
        if t == "apiKey":
            auth_type = AuthType.API_KEY
        elif t == "oauth2":
            auth_type = AuthType.OAUTH2
        elif t == "http" and scheme.get("scheme") == "bearer":
            auth_type = AuthType.BEARER
        else:
            auth_type = AuthType.BEARER
            loss.coerced_fields.append("auth.type")
            loss.notes.append(
                f"securitySchemes.{first_name}.type={t!r} approximated as bearer."
            )
    scopes: List[str] = []
    token_url = scheme.get("x-uap-token-url")
    auth_url = scheme.get("x-uap-authorize-url")
    if auth_type == AuthType.OAUTH2:
        flows = scheme.get("flows") or {}
        if isinstance(flows, dict):
            for flow_name in ("authorizationCode", "clientCredentials", "implicit", "password"):
                flow = flows.get(flow_name)
                if isinstance(flow, dict):
                    if not token_url and flow.get("tokenUrl"):
                        token_url = flow["tokenUrl"]
                    if not auth_url and flow.get("authorizationUrl"):
                        auth_url = flow["authorizationUrl"]
                    flow_scopes = flow.get("scopes") or {}
                    if isinstance(flow_scopes, dict):
                        scopes = list(flow_scopes.keys())
                    break
    secret_ref = scheme.get("x-uap-secret-ref")
    header_name = scheme.get("x-uap-header-name") or scheme.get("name")
    audience = scheme.get("x-uap-audience")
    try:
        return AuthConfig(
            type=auth_type,
            scopes=scopes,
            token_url=token_url,
            authorize_url=auth_url,
            audience=audience,
            header_name=header_name if auth_type in (AuthType.API_KEY, AuthType.BEARER) else None,
            secret_ref=secret_ref,
        )
    except ValueError as exc:
        loss.dropped_fields.append("auth.secret_ref")
        loss.notes.append(
            f"AuthConfig rejected secret_ref={secret_ref!r}: {exc}"
        )
        return AuthConfig(
            type=auth_type,
            scopes=scopes,
            token_url=token_url,
            authorize_url=auth_url,
            audience=audience,
            header_name=header_name if auth_type in (AuthType.API_KEY, AuthType.BEARER) else None,
        )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def agent_from_openapi(spec: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Reconstruct a UAP :class:`Agent` from an OpenAPI 3.x document."""
    if not isinstance(spec, dict):
        raise TypeError(
            f"agent_from_openapi expected a dict, got {type(spec).__name__}"
        )
    version_field = spec.get("openapi")
    if not isinstance(version_field, str) or not version_field.startswith("3."):
        raise ValueError(
            f"agent_from_openapi only accepts OpenAPI 3.x; got openapi={version_field!r}"
        )

    loss = LossInfo()
    info = spec.get("info") or {}
    if not isinstance(info, dict):
        info = {}

    title = str(info.get("title") or "agent")
    description = str(info.get("description") or "")
    version = str(info.get("version") or "0.1.0")

    urn = info.get("x-uap-urn")
    if isinstance(urn, str) and urn.startswith("urn:uap:agent:"):
        agent_id = urn
    else:
        agent_id = f"urn:uap:agent:{_slugify(title)}"
        loss.notes.append(
            f"info.x-uap-urn missing; synthesized agent URN {agent_id!r} from title."
        )

    name = info.get("x-uap-name") or _slugify(title).replace("-", "_") or "agent"
    name = str(name)
    if not (name[:1].isalpha() or name[:1] == "_"):
        name = f"a_{name}"
    display_name = info.get("x-uap-display-name") or title

    capabilities = _restore_capabilities(info.get("x-uap-capabilities"), loss)
    compliance = _restore_compliance(info.get("x-uap-compliance"), loss)
    ui = _restore_ui(info.get("x-uap-ui"))
    tags_ext = info.get("x-uap-tags")
    tags = [str(t) for t in tags_ext] if isinstance(tags_ext, list) else []
    metadata_raw = info.get("x-uap-metadata") or {}
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
    publisher = info.get("x-uap-publisher")
    homepage = info.get("x-uap-homepage")
    documentation_url = info.get("x-uap-documentation-url")
    skills_raw = info.get("x-uap-skills") or []
    skills: List[Skill] = []
    if isinstance(skills_raw, list):
        for s in skills_raw:
            if isinstance(s, dict):
                try:
                    skills.append(Skill(**s))
                except Exception:  # pragma: no cover — defensive
                    continue

    # Endpoints from servers.
    endpoints: List[Endpoint] = []
    servers = spec.get("servers") or []
    if isinstance(servers, list):
        for srv in servers:
            if not isinstance(srv, dict):
                continue
            url = srv.get("url")
            if not url:
                continue
            extras = srv.get("x-uap-endpoint") or {}
            if isinstance(extras, dict) and extras:
                merged = {"url": url, **extras}
                try:
                    endpoints.append(Endpoint(**merged))
                    continue
                except Exception:  # pragma: no cover — defensive
                    pass
            endpoints.append(Endpoint(transport=Transport.HTTP, url=url))

    # Auth.
    components = spec.get("components") or {}
    if not isinstance(components, dict):
        components = {}
    auth = _restore_auth(components, loss)

    # Tools — iterate over every operation.
    tools: List[Tool] = []
    paths = spec.get("paths") or {}
    if isinstance(paths, dict):
        for path, methods in paths.items():
            if not isinstance(methods, dict):
                continue
            for method, op in methods.items():
                if method.lower() not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                    "trace",
                }:
                    continue
                if not isinstance(op, dict):
                    continue
                try:
                    tools.append(_tool_from_operation(str(path), str(method), op, loss))
                except Exception as exc:
                    loss.dropped_fields.append(f"paths.{path}.{method}")
                    loss.notes.append(
                        f"Failed to build tool from {method.upper()} {path}: {exc!r}"
                    )

    # Smuggled URN tool references.
    tool_refs = info.get("x-uap-tool-refs")
    extra_tool_entries: List[Any] = []
    if isinstance(tool_refs, list):
        for t in tool_refs:
            if isinstance(t, str) and t.startswith("urn:uap:tool:"):
                extra_tool_entries.append(t)

    agent = Agent(
        id=agent_id,
        name=name,
        display_name=display_name,
        description=description,
        version=version,
        tools=[*tools, *extra_tool_entries],
        skills=skills,
        endpoints=endpoints,
        auth=auth,
        capabilities=capabilities,
        compliance=compliance,
        ui=ui,
        publisher=publisher,
        homepage=homepage,
        documentation_url=documentation_url,
        tags=tags,
        metadata=metadata,
    )

    return agent, loss


def from_openapi(spec: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Alias for :func:`agent_from_openapi`."""
    return agent_from_openapi(spec)
