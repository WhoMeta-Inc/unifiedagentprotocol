# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip tests for the UAP <-> OpenAPI v3 bridge."""
from __future__ import annotations

import pytest

from unifiedagentprotocol.bridges.openapi import from_openapi, to_openapi
from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    AuthType,
    Capabilities,
    Compliance,
    DataClassification,
    Endpoint,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    PIILevel,
    SideEffects,
    Tool,
    Transport,
)


def _make_agent_with_envelope() -> Agent:
    """Build an Agent exercising capabilities, compliance, auth and a tool."""
    body_param = Parameter(
        name="city",
        schema=ParameterSchema(type="string", description="Target city"),
        required=True,
        location=ParameterLocation.BODY,
    )
    tool = Tool(
        id="urn:uap:tool:get-weather",
        name="get_weather",
        display_name="Get Weather",
        description="Fetches the current weather for a city.",
        version="1.2.0",
        parameters=[body_param],
        capabilities=Capabilities(
            idempotent=True,
            side_effects=SideEffects.READ_ONLY,
            deterministic=True,
            requires_human_approval=False,
        ),
        compliance=Compliance(
            data_classification=DataClassification.PUBLIC,
            pii=PIILevel.NONE,
            regulations=["GDPR"],
            data_residency=["EU"],
        ),
        tags=["weather", "public"],
    )
    return Agent(
        id="urn:uap:agent:weather-bot",
        name="weather_bot",
        display_name="Weather Bot",
        description="Bot exposing weather tools.",
        version="1.0.0",
        tools=[tool],
        endpoints=[Endpoint(transport=Transport.HTTP, url="https://api.example.com/v1")],
        auth=AuthConfig(type=AuthType.BEARER, secret_ref="vault://kv/data/weather#token"),
        capabilities=Capabilities(
            idempotent=False,
            side_effects=SideEffects.READ_ONLY,
            deterministic=True,
            requires_human_approval=False,
            supports_streaming=True,
        ),
        compliance=Compliance(
            data_classification=DataClassification.CONFIDENTIAL,
            pii=PIILevel.LOW,
            regulations=["SOC2"],
            data_residency=["EU"],
            retention_days=30,
        ),
    )


def test_agent_roundtrip_preserves_uap_fields_via_x_extensions() -> None:
    """Capabilities + compliance survive because of ``x-uap-*`` extensions."""
    agent = _make_agent_with_envelope()
    spec, _ = to_openapi(agent)

    # Sanity: it's a valid OpenAPI 3.0.3 document at the top level.
    assert spec["openapi"].startswith("3.")
    assert "info" in spec
    assert "paths" in spec
    # x-uap-* extensions live on info and on each operation.
    assert spec["info"]["x-uap-urn"] == agent.id
    assert "x-uap-capabilities" in spec["info"]
    assert "x-uap-compliance" in spec["info"]
    # Operation also carries enterprise extensions.
    (path, methods) = next(iter(spec["paths"].items()))
    op = methods["post"]
    assert op["x-uap-urn"].startswith("urn:uap:tool:")
    assert op["x-uap-capabilities"]["idempotent"] is True
    assert op["x-uap-compliance"]["regulations"] == ["GDPR"]

    restored, _ = from_openapi(spec)
    assert restored.id == agent.id
    assert restored.name == agent.name
    assert restored.description == agent.description
    # Enterprise fields recovered.
    assert restored.capabilities.supports_streaming is True
    assert restored.capabilities.side_effects is SideEffects.READ_ONLY
    assert restored.compliance.data_classification is DataClassification.CONFIDENTIAL
    assert restored.compliance.regulations == ["SOC2"]
    assert restored.compliance.retention_days == 30
    # Auth survived through securityScheme + x-uap-* hints.
    assert restored.auth is not None
    assert restored.auth.type is AuthType.BEARER
    assert restored.auth.secret_ref == "vault://kv/data/weather#token"
    # Tool survived with its own envelope.
    assert len(restored.tools) == 1
    rtool = restored.tools[0]
    assert isinstance(rtool, Tool)
    assert rtool.id == "urn:uap:tool:get-weather"
    assert rtool.capabilities.idempotent is True
    assert rtool.compliance.data_classification is DataClassification.PUBLIC


def test_path_query_header_locations_survive() -> None:
    """Tool params with locations path/query/header survive a round-trip."""
    path_p = Parameter(
        name="user_id",
        schema=ParameterSchema(type="string"),
        required=True,
        location=ParameterLocation.PATH,
    )
    query_p = Parameter(
        name="verbose",
        schema=ParameterSchema(type="boolean"),
        required=False,
        location=ParameterLocation.QUERY,
    )
    header_p = Parameter(
        name="x_trace_id",
        schema=ParameterSchema(type="string"),
        required=False,
        location=ParameterLocation.HEADER,
    )
    body_p = Parameter(
        name="payload",
        schema=ParameterSchema(type="string"),
        required=True,
        location=ParameterLocation.BODY,
    )
    tool = Tool(
        id="urn:uap:tool:mixed-params",
        name="mixed_params",
        description="A tool with mixed-location params.",
        parameters=[path_p, query_p, header_p, body_p],
    )
    agent = Agent(
        id="urn:uap:agent:mixed",
        name="mixed",
        description="Mixed param agent.",
        tools=[tool],
    )

    spec, _ = to_openapi(agent)
    # The synthesized path embeds the path parameter.
    op_path = next(iter(spec["paths"].keys()))
    assert "{user_id}" in op_path
    # parameters list carries query/header/path
    op = spec["paths"][op_path]["post"]
    op_params = op.get("parameters") or []
    locs = {(p["name"], p["in"]) for p in op_params}
    assert ("user_id", "path") in locs
    assert ("verbose", "query") in locs
    assert ("x_trace_id", "header") in locs
    # body param ended up in requestBody.
    assert (
        op["requestBody"]["content"]["application/json"]["schema"]["properties"][
            "payload"
        ]["type"]
        == "string"
    )

    restored, _ = from_openapi(spec)
    rtool = restored.tools[0]
    assert isinstance(rtool, Tool)
    by_name = {p.name: p for p in rtool.parameters}
    assert by_name["user_id"].location is ParameterLocation.PATH
    assert by_name["verbose"].location is ParameterLocation.QUERY
    assert by_name["x_trace_id"].location is ParameterLocation.HEADER
    assert by_name["payload"].location is ParameterLocation.BODY


def test_rejects_v2() -> None:
    """``from_openapi`` must reject a Swagger 2.0 doc."""
    with pytest.raises(ValueError):
        from_openapi({"swagger": "2.0"})
