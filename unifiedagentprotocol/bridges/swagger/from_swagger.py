# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Swagger v2.0 -> UAP import."""
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
# JSON-Schema-ish helpers (Swagger schemas are a subset of JSON Schema)
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


# ---------------------------------------------------------------------------
# Parameter conversion
# ---------------------------------------------------------------------------

_LOCATION_MAP: Dict[str, ParameterLocation] = {
    "path": ParameterLocation.PATH,
    "query": ParameterLocation.QUERY,
    "header": ParameterLocation.HEADER,
    "body": ParameterLocation.BODY,
    "formData": ParameterLocation.BODY,
}


def _swagger_parameter_to_uap(
    entry: Dict[str, Any], loss: LossInfo, idx: int
) -> List[Parameter]:
    """Translate one Swagger v2 parameter entry into UAP Parameters."""
    where = entry.get("in")
    name = entry.get("name")
    if not where or not name:
        loss.dropped_fields.append(f"parameters[{idx}]")
        return []
    loc = _LOCATION_MAP.get(where)
    if loc is None:
        loss.dropped_fields.append(f"parameters[{idx}].in={where!r}")
        loss.notes.append(
            f"Swagger parameter location {where!r} is not modelled by UAP; dropped."
        )
        return []

    if where == "body":
        # body parameter encodes a full schema (object) — fan it out.
        schema = entry.get("schema") or {}
        if isinstance(schema, dict) and schema.get("type") == "object" and isinstance(schema.get("properties"), dict):
            return _decompose_body_object(schema, loss)
        # else treat as a single anonymous body parameter
        return [
            Parameter(
                name=str(name),
                schema=_to_parameter_schema(schema if isinstance(schema, dict) else {}),
                required=bool(entry.get("required", False)),
                location=ParameterLocation.BODY,
                description=entry.get("description"),
            )
        ]
    if where == "formData":
        loss.coerced_fields.append(f"parameters[{idx}].in")
        loss.notes.append(
            f"Swagger 'formData' parameter {name!r} folded into body."
        )

    # Primitive parameter: build a schema from the leaf type fields.
    # Note: ``required`` at the parameter entry top level is a *boolean*
    # flag (consumed below to set ``Parameter.required``), not the
    # JSON-Schema list. Inside ``entry["schema"]`` it is the JSON-Schema
    # array form and is preserved.
    primitive_schema_dict: Dict[str, Any] = {}
    for k in _SCHEMA_KEYS:
        if k == "required":
            continue
        if k in entry:
            primitive_schema_dict[k] = entry[k]
    if "schema" in entry and isinstance(entry["schema"], dict):
        for k, v in entry["schema"].items():
            if k in _SCHEMA_KEYS:
                primitive_schema_dict[k] = v
    return [
        Parameter(
            name=str(name),
            schema=_to_parameter_schema(primitive_schema_dict),
            required=bool(entry.get("required", where == "path")),
            location=loc,
            description=entry.get("description"),
        )
    ]


def _decompose_body_object(schema: Dict[str, Any], loss: LossInfo) -> List[Parameter]:
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    out: List[Parameter] = []
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


# ---------------------------------------------------------------------------
# x-uap-* restoration helpers (mirrors openapi)
# ---------------------------------------------------------------------------

def _restore_capabilities(raw: Any) -> Capabilities:
    if isinstance(raw, dict):
        try:
            return Capabilities(**raw)
        except Exception:  # pragma: no cover — defensive
            return Capabilities()
    return Capabilities()


def _restore_compliance(raw: Any) -> Compliance:
    if isinstance(raw, dict):
        try:
            return Compliance(**raw)
        except Exception:  # pragma: no cover — defensive
            return Compliance()
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


# ---------------------------------------------------------------------------
# Operation -> Tool
# ---------------------------------------------------------------------------

def _tool_from_operation(
    path: str,
    method: str,
    op: Dict[str, Any],
    inherited_params: List[Dict[str, Any]],
    loss: LossInfo,
) -> Tool:
    # Merge path-level + operation-level params (operation overrides on name+in).
    combined: List[Dict[str, Any]] = []
    seen: set = set()
    for entry in (op.get("parameters") or []):
        if not isinstance(entry, dict):
            continue
        key = (entry.get("name"), entry.get("in"))
        seen.add(key)
        combined.append(entry)
    for entry in inherited_params:
        if not isinstance(entry, dict):
            continue
        key = (entry.get("name"), entry.get("in"))
        if key not in seen:
            combined.append(entry)

    params: List[Parameter] = []
    for idx, entry in enumerate(combined):
        params.extend(_swagger_parameter_to_uap(entry, loss, idx))

    # Apply x-uap-param-locations for round-trip fidelity.
    locations: Dict[str, str] = op.get("x-uap-param-locations") or {}
    required_flags: Dict[str, bool] = op.get("x-uap-param-required") or {}
    for p in params:
        loc = locations.get(p.name)
        if loc and loc != p.location.value:
            try:
                p.location = ParameterLocation(loc)
            except ValueError:
                loss.coerced_fields.append(f"parameters[{p.name}].location")
        if p.name in required_flags:
            p.required = bool(required_flags[p.name])

    # Output from responses.200.schema
    response_schema: Optional[Dict[str, Any]] = None
    responses = op.get("responses") or {}
    if isinstance(responses, dict):
        ok = responses.get("200") or responses.get(200)
        if isinstance(ok, dict):
            sch = ok.get("schema")
            if isinstance(sch, dict):
                response_schema = sch
    output: Optional[OutputSchema] = None
    if isinstance(response_schema, dict):
        output = OutputSchema(schema=_to_parameter_schema(response_schema))

    # Identity
    urn = op.get("x-uap-urn")
    if isinstance(urn, str) and urn.startswith("urn:uap:tool:"):
        tool_id = urn
    else:
        op_id = op.get("operationId") or f"{method}_{path}"
        tool_id = f"urn:uap:tool:{_slugify(op_id)}"

    name_raw = op.get("x-uap-name") or op.get("operationId") or f"{method}_{path}"
    name_safe = re.sub(r"[^A-Za-z0-9_]+", "_", str(name_raw)).strip("_") or "tool"
    if name_safe[0].isdigit():
        name_safe = f"t_{name_safe}"

    description = op.get("description") or op.get("summary") or ""
    version = str(op.get("x-uap-version") or "0.1.0")
    display_name = op.get("x-uap-display-name") or op.get("summary")

    capabilities = _restore_capabilities(op.get("x-uap-capabilities"))
    compliance = _restore_compliance(op.get("x-uap-compliance"))
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

def _restore_auth(spec: Dict[str, Any], loss: LossInfo) -> Optional[AuthConfig]:
    defs = spec.get("securityDefinitions") or {}
    if not isinstance(defs, dict) or not defs:
        return None
    first_name, scheme = next(iter(defs.items()))
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
        t = scheme.get("type")
        if t == "apiKey":
            auth_type = AuthType.API_KEY
        elif t == "oauth2":
            auth_type = AuthType.OAUTH2
        elif t == "basic":
            auth_type = AuthType.BEARER
            loss.coerced_fields.append("auth.type")
            loss.notes.append(
                f"securityDefinitions.{first_name}.type='basic' approximated as bearer."
            )
        else:
            auth_type = AuthType.BEARER
            loss.coerced_fields.append("auth.type")

    scopes_raw = scheme.get("scopes")
    scopes: List[str] = (
        list(scopes_raw.keys()) if isinstance(scopes_raw, dict) else []
    )
    token_url = scheme.get("tokenUrl") or scheme.get("x-uap-token-url")
    auth_url = scheme.get("authorizationUrl") or scheme.get("x-uap-authorize-url")
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

def agent_from_swagger(spec: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Parse a Swagger 2.0 dict into a UAP :class:`Agent`."""
    if not isinstance(spec, dict):
        raise TypeError(
            f"agent_from_swagger expected a dict, got {type(spec).__name__}"
        )
    version_field = spec.get("swagger")
    if version_field != "2.0":
        raise ValueError(
            f"agent_from_swagger only accepts swagger='2.0'; got swagger={version_field!r}"
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

    capabilities = _restore_capabilities(info.get("x-uap-capabilities"))
    compliance = _restore_compliance(info.get("x-uap-compliance"))
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

    # Endpoint synthesis from host + basePath + schemes.
    endpoints: List[Endpoint] = []
    host = spec.get("host")
    base_path = spec.get("basePath") or ""
    schemes = spec.get("schemes") or ["https"]
    if host:
        scheme_choice = "https" if "https" in schemes else schemes[0]
        url = f"{scheme_choice}://{host}{base_path}"
        endpoints.append(Endpoint(transport=Transport.HTTP, url=url))

    # Auth.
    auth = _restore_auth(spec, loss)

    # Tools.
    tools: List[Tool] = []
    paths = spec.get("paths") or {}
    if isinstance(paths, dict):
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            inherited = path_item.get("parameters") or []
            if not isinstance(inherited, list):
                inherited = []
            for method, op in path_item.items():
                if method.lower() not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                }:
                    continue
                if not isinstance(op, dict):
                    continue
                try:
                    tools.append(
                        _tool_from_operation(
                            str(path), str(method), op, inherited, loss
                        )
                    )
                except Exception as exc:
                    loss.dropped_fields.append(f"paths.{path}.{method}")
                    loss.notes.append(
                        f"Failed to build tool from {method.upper()} {path}: {exc!r}"
                    )

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


def from_swagger(spec: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Alias for :func:`agent_from_swagger`."""
    return agent_from_swagger(spec)
