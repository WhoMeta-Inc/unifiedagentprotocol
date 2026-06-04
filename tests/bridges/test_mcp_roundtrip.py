# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip and shape tests for the UAP <-> MCP bridge."""
from __future__ import annotations

from typing import Any, Dict

import jsonschema
import pytest

from unifiedagentprotocol.bridges.mcp import (
    from_mcp,
    from_mcp_tool,
    to_mcp,
    to_mcp_tool,
)
from unifiedagentprotocol.bridges.mcp.from_mcp import (
    agent_from_mcp,
    tool_from_mcp,
)
from unifiedagentprotocol.bridges.mcp.to_mcp import (
    agent_to_mcp,
    tool_to_mcp,
)
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
    PIILevel,
    SideEffects,
    Skill,
    Tool,
    Transport,
    Trigger,
    TriggerType,
    UIConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Field paths used by ``model_dump(include=...)`` for round-trip equality.
# These are exactly the UAP fields that the MCP bridge represents losslessly.
_TOOL_REPRESENTABLE_FIELDS = {
    "id",
    "name",
    "display_name",
    "description",
    "version",
    "parameters",
    "output",
    "endpoint",
    "auth",
    "capabilities",
    "compliance",
    "cost",
    "ui",
    "tags",
    "metadata",
}


def _make_lossless_tool() -> Tool:
    """Build a UAP Tool that uses only MCP-representable fields."""
    return Tool(
        id="urn:uap:tool:get-weather",
        name="get_weather",
        display_name="Get Weather",
        description="Look up the current weather for a city.",
        version="1.2.0",
        parameters=[
            Parameter(
                name="city",
                schema=ParameterSchema(
                    type="string",
                    description="Target city.",
                    enum=["paris", "berlin", "tokyo"],
                    min_length=1,
                ),
                required=True,
            ),
            Parameter(
                name="days",
                schema=ParameterSchema(
                    type="integer",
                    description="Forecast horizon in days.",
                    minimum=1,
                    maximum=10,
                    default=1,
                ),
                required=False,
            ),
        ],
        endpoint=Endpoint(
            transport=Transport.HTTP,
            url="https://api.weather.example/v1/forecast",
            method="POST",
        ),
        auth=AuthConfig(
            type=AuthType.BEARER,
            secret_ref="vault://kv/data/weather#token",
        ),
        capabilities=Capabilities(
            idempotent=True,
            side_effects=SideEffects.READ_ONLY,
            deterministic=False,
            requires_human_approval=False,
        ),
        compliance=Compliance(
            pii=PIILevel.LOW,
            regulations=["GDPR"],
        ),
        cost=CostHint(currency="USD", per_call_usd=0.0001, latency_ms_p50=200),
        ui=UIConfig(label="Get Weather", icon="mdi:weather-partly-cloudy"),
        tags=["weather", "public"],
        metadata={"team": "weather-team"},
    )


def _make_lossy_tool() -> Tool:
    """Build a Tool whose fields are not all MCP-representable."""
    return Tool(
        id="urn:uap:tool:nightly-report",
        name="nightly_report",
        description="Run the nightly report.",
        parameters=[
            Parameter(
                name="day",
                schema=ParameterSchema(type="string", format="date"),
                required=True,
            ),
        ],
        triggers=[
            Trigger(type=TriggerType.CRON, cron="0 2 * * *", description="Nightly"),
        ],
        auth=AuthConfig(
            type=AuthType.MTLS,
            secret_ref="vault://kv/data/mtls#cert",
        ),
        compliance=Compliance(
            data_residency=["EU"],
            regulations=["GDPR"],
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tool_roundtrip_lossless() -> None:
    """A Tool using only MCP-representable fields round-trips with no loss."""
    original = _make_lossless_tool()

    mcp_tool, loss_out = tool_to_mcp(original)
    assert isinstance(mcp_tool, dict)
    assert mcp_tool["name"] == "get_weather"
    assert mcp_tool["description"].startswith("Look up the current weather")
    assert mcp_tool["inputSchema"]["type"] == "object"
    assert "annotations" in mcp_tool

    # No loss expected: ``data_residency`` is empty, no triggers, supported
    # auth and supported endpoint transport.
    assert not loss_out.dropped_fields, loss_out.dropped_fields
    assert not loss_out.coerced_fields, loss_out.coerced_fields

    restored, loss_in = tool_from_mcp(mcp_tool)

    original_dump = original.model_dump(
        mode="json", include=_TOOL_REPRESENTABLE_FIELDS
    )
    restored_dump = restored.model_dump(
        mode="json", include=_TOOL_REPRESENTABLE_FIELDS
    )
    assert restored_dump == original_dump
    assert not loss_in.dropped_fields
    assert not loss_in.coerced_fields


def test_tool_roundtrip_records_losses() -> None:
    """Cron triggers, mTLS auth, and data_residency are all reported as lost."""
    original = _make_lossy_tool()

    mcp_tool, loss = tool_to_mcp(original)

    # cron trigger dropped
    assert "triggers[0]" in loss.dropped_fields
    # mTLS auth dropped
    assert "auth" in loss.dropped_fields
    # data residency dropped
    assert "compliance.data_residency" in loss.dropped_fields

    # Free-form notes confirm the reasons.
    joined = " ".join(loss.notes).lower()
    assert "trigger" in joined
    assert "mtls" in joined
    assert "data_residency" in joined

    # The MCP output must omit the unrepresentable annotation fields.
    annotations = mcp_tool["annotations"]
    assert "x-uap-auth" not in annotations
    compliance_payload = annotations["x-uap-compliance"]
    assert "data_residency" not in compliance_payload


def test_agent_roundtrip() -> None:
    """An Agent with two inline tools survives ``from_mcp(to_mcp(a)[0])``."""
    tool_a = _make_lossless_tool()
    tool_b = Tool(
        id="urn:uap:tool:list-stations",
        name="list_stations",
        description="List nearby weather stations.",
        parameters=[
            Parameter(
                name="country",
                schema=ParameterSchema(type="string"),
                required=True,
            ),
        ],
    )

    agent = Agent(
        id="urn:uap:agent:weather-bot",
        name="weather_bot",
        display_name="Weather Bot",
        description="Surfaces public weather APIs.",
        version="2.0.0",
        tools=[tool_a, tool_b],
        skills=[
            Skill(
                id="forecast",
                name="forecast",
                description="Multi-day weather forecast.",
            )
        ],
        endpoints=[
            Endpoint(
                transport=Transport.HTTP,
                url="https://api.weather.example/mcp",
                method="POST",
            ),
        ],
        capabilities=Capabilities(supports_streaming=True),
        publisher="Acme",
        homepage="https://acme.example",
        tags=["weather"],
    )

    mcp_server, loss_out = agent_to_mcp(agent)
    assert mcp_server["name"] == "weather_bot"
    assert mcp_server["version"] == "2.0.0"
    assert mcp_server["resources"] == []
    assert mcp_server["prompts"] == []
    assert len(mcp_server["tools"]) == 2
    assert {t["name"] for t in mcp_server["tools"]} == {
        "get_weather",
        "list_stations",
    }
    assert not loss_out.dropped_fields, loss_out.dropped_fields

    restored, loss_in = agent_from_mcp(mcp_server)

    assert restored.id == agent.id
    assert restored.name == agent.name
    assert restored.display_name == agent.display_name
    assert restored.description == agent.description
    assert restored.version == agent.version
    assert restored.publisher == "Acme"
    assert restored.homepage == "https://acme.example"
    assert restored.tags == ["weather"]
    assert restored.capabilities.supports_streaming is True

    # Skills survive.
    assert len(restored.skills) == 1
    assert restored.skills[0].id == "forecast"

    # Endpoints survive.
    assert len(restored.endpoints) == 1
    assert restored.endpoints[0].url == "https://api.weather.example/mcp"

    # Tools survive in order, with their representable fields intact.
    assert len(restored.tools) == 2
    assert isinstance(restored.tools[0], Tool)
    assert isinstance(restored.tools[1], Tool)
    assert restored.tools[0].id == "urn:uap:tool:get-weather"
    assert restored.tools[1].id == "urn:uap:tool:list-stations"

    # No loss expected on the agent-level fields either.
    assert not loss_in.dropped_fields
    assert not loss_in.coerced_fields


def test_mcp_inputSchema_is_valid_json_schema() -> None:
    """The produced ``inputSchema`` validates well-formed sample calls."""
    tool = _make_lossless_tool()
    mcp_tool, _ = tool_to_mcp(tool)

    input_schema: Dict[str, Any] = mcp_tool["inputSchema"]

    # ``inputSchema`` must itself be a valid JSON Schema by Draft 2020-12.
    jsonschema.Draft202012Validator.check_schema(input_schema)

    # Valid call: required ``city`` present.
    valid_call = {"city": "berlin", "days": 3}
    jsonschema.validate(instance=valid_call, schema=input_schema)

    # Invalid call: missing required ``city``.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance={"days": 1}, schema=input_schema)

    # Invalid call: wrong enum value.
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance={"city": "atlantis", "days": 1},
            schema=input_schema,
        )


def test_synthesizes_urn_on_import() -> None:
    """Importing an MCP payload with no UAP id still yields a valid URN."""
    # Tool with no x-uap-id annotation.
    raw_tool: Dict[str, Any] = {
        "name": "Search Web!!",  # contains characters that need slugification
        "description": "Search the public web.",
        "inputSchema": {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    }
    tool, _ = tool_from_mcp(raw_tool)
    assert tool.id.startswith("urn:uap:tool:")
    # Slugified deterministically: lowercase, non-alnum -> "-".
    assert tool.id == "urn:uap:tool:search-web"
    # The URN validator on Tool.id accepted the result.

    # Server descriptor with no x-uap-id annotation.
    raw_server: Dict[str, Any] = {
        "name": "Helpful Agent",
        "version": "0.1.0",
        "description": "A friendly helper.",
        "tools": [],
    }
    agent, _ = agent_from_mcp(raw_server)
    assert agent.id.startswith("urn:uap:agent:")
    assert agent.id == "urn:uap:agent:helpful-agent"


# ---------------------------------------------------------------------------
# Sanity / dispatch tests
# ---------------------------------------------------------------------------


def test_dispatch_to_mcp_handles_both_kinds() -> None:
    """``to_mcp`` dispatches to the right inner function."""
    tool = _make_lossless_tool()
    out_tool, _ = to_mcp(tool)
    assert "inputSchema" in out_tool

    agent = Agent(
        id="urn:uap:agent:empty",
        name="empty",
        description="empty agent",
        version="0.1.0",
    )
    out_agent, _ = to_mcp(agent)
    assert out_agent["resources"] == []
    assert out_agent["prompts"] == []


def test_dispatch_from_mcp_detects_kind() -> None:
    """``from_mcp`` autodetects Tool vs server payloads."""
    tool = _make_lossless_tool()
    mcp_tool, _ = tool_to_mcp(tool)
    restored, _ = from_mcp(mcp_tool)
    assert isinstance(restored, Tool)

    agent = Agent(
        id="urn:uap:agent:empty",
        name="empty",
        description="empty agent",
        version="0.1.0",
    )
    mcp_server, _ = agent_to_mcp(agent)
    restored_agent, _ = from_mcp(mcp_server)
    assert isinstance(restored_agent, Agent)


def test_to_mcp_tool_alias_matches_inner() -> None:
    """The public ``to_mcp_tool`` / ``from_mcp_tool`` aliases call through."""
    tool = _make_lossless_tool()
    via_alias, _ = to_mcp_tool(tool)
    via_inner, _ = tool_to_mcp(tool)
    assert via_alias == via_inner

    via_alias_back, _ = from_mcp_tool(via_alias)
    via_inner_back, _ = tool_from_mcp(via_inner)
    assert via_alias_back.model_dump() == via_inner_back.model_dump()


def test_loss_info_returned_is_lossinfo_type() -> None:
    """Both API entry points return a real :class:`LossInfo` instance."""
    _, loss_tool = tool_to_mcp(_make_lossless_tool())
    assert isinstance(loss_tool, LossInfo)

    agent = Agent(
        id="urn:uap:agent:empty",
        name="empty",
        description="empty agent",
        version="0.1.0",
    )
    _, loss_agent = agent_to_mcp(agent)
    assert isinstance(loss_agent, LossInfo)
