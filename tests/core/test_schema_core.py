# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Core schema integrity tests — Pydantic v2, validation, round-trip."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from unifiedagentprotocol import (
    Agent,
    AuthConfig,
    AuthType,
    Capabilities,
    Compliance,
    CostHint,
    DataClassification,
    Endpoint,
    Envelope,
    Kind,
    LossInfo,
    Manifest,
    PIILevel,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    SideEffects,
    Skill,
    Tool,
    Transport,
    Trigger,
    TriggerType,
    UAP_VERSION,
    UIConfig,
)


def _tool() -> Tool:
    return Tool(
        id="urn:uap:tool:get-weather",
        name="get_weather",
        description="Fetch weather",
        parameters=[
            Parameter(
                name="city",
                schema=ParameterSchema(type="string", min_length=1, max_length=100),
                required=True,
                location=ParameterLocation.BODY,
            ),
        ],
        capabilities=Capabilities(
            idempotent=True,
            side_effects=SideEffects.READ_ONLY,
            deterministic=False,
            requires_human_approval=False,
        ),
        auth=AuthConfig(type=AuthType.API_KEY, secret_ref="vault://kv/weather#token"),
        compliance=Compliance(
            data_classification=DataClassification.PUBLIC,
            pii=PIILevel.NONE,
            regulations=["GDPR"],
            data_residency=["EU"],
        ),
        cost=CostHint(per_call_usd=0.0001, latency_ms_p50=120, latency_ms_p99=900),
        endpoint=Endpoint(
            transport=Transport.HTTP,
            url="https://api.example.com/weather",
            method="POST",
        ),
        triggers=[Trigger(type=TriggerType.INTENT, intent_pattern="^/weather")],
        ui=UIConfig(label="Weather"),
        tags=["weather", "public"],
    )


def _agent(tool: Tool) -> Agent:
    return Agent(
        id="urn:uap:agent:weather-bot",
        name="WeatherBot",
        description="Provides weather information",
        tools=[tool],
        skills=[
            Skill(
                id="answer-weather",
                name="answer-weather",
                description="Reply with current weather for a city",
            )
        ],
        endpoints=[Endpoint(transport=Transport.HTTP, url="https://bot.example.com")],
    )


def test_tool_roundtrip():
    t = _tool()
    assert Tool.model_validate(t.model_dump()) == t


def test_agent_roundtrip():
    a = _agent(_tool())
    assert Agent.model_validate(a.model_dump()) == a


def test_envelope_wraps_payload():
    env = Envelope.of(_agent(_tool()))
    assert env.kind == Kind.AGENT
    assert env.uap_version == UAP_VERSION
    wire = env.to_wire()
    assert "payload" in wire
    assert wire["kind"] == "agent"


def test_envelope_rejects_incompatible_version():
    with pytest.raises(ValidationError):
        Envelope(
            uap_version="2.0",
            kind=Kind.TOOL,
            id="urn:uap:tool:x",
            payload=_tool(),
        )


def test_urn_validation():
    with pytest.raises(ValidationError):
        Tool(id="not-a-urn", name="x", description="x")
    with pytest.raises(ValidationError):
        Tool(id="urn:uap:agent:x", name="x", description="x")  # wrong kind


def test_secret_ref_rejects_inline():
    with pytest.raises(ValidationError):
        AuthConfig(type=AuthType.API_KEY, secret_ref="sk-not-allowed-inline")


def test_secret_ref_accepts_vault_ref():
    cfg = AuthConfig(type=AuthType.API_KEY, secret_ref="vault://kv/data/x#token")
    assert cfg.secret_ref.startswith("vault://")


def test_parameter_schema_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ParameterSchema(type="bogus")


def test_trigger_requires_field_for_cron():
    with pytest.raises(ValidationError):
        Trigger(type=TriggerType.CRON)
    t = Trigger(type=TriggerType.CRON, cron="0 */6 * * *")
    assert t.cron == "0 */6 * * *"


def test_endpoint_method_normalized():
    e = Endpoint(transport=Transport.HTTP, url="https://x", method="post")
    assert e.method == "POST"


def test_loss_info_helpers():
    a = LossInfo(dropped_fields=["x"], notes=["a"])
    b = LossInfo(coerced_fields=["y"], notes=["b"])
    c = a.merge(b)
    assert c.dropped_fields == ["x"]
    assert c.coerced_fields == ["y"]
    assert c.notes == ["a", "b"]
    assert c.is_lossy() is True
    assert LossInfo().is_lossy() is False


def test_manifest_carries_agents_and_tools():
    m = Manifest(
        id="urn:uap:manifest:weather-suite",
        name="Weather Suite",
        description="bundle",
        agents=[_agent(_tool())],
        tools=[_tool()],
    )
    assert Manifest.model_validate(m.model_dump()) == m


def test_wire_format_excludes_none():
    t = _tool()
    wire = Envelope.of(t).to_wire()
    # produced_by always present, signature was None → excluded
    assert "signature" not in wire
    assert "produced_by" in wire


def test_capabilities_defaults_are_safe():
    """Defaults bias toward the cautious choice."""
    c = Capabilities()
    assert c.idempotent is False
    assert c.side_effects == SideEffects.WRITES
    assert c.requires_human_approval is True
