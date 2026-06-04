# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""HTTP-level tests for the FastAPI runtime adapter.

These tests exercise the public API surface produced by
``runtime.create_app``. They are skipped wholesale when FastAPI is not
installed so the rest of the test suite stays runnable in minimal
environments.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from unifiedagentprotocol.core import (
    Agent,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    SDK_VERSION,
    Skill,
    Tool,
    UAP_VERSION,
)
from unifiedagentprotocol.registry_impl import InMemoryRegistry
from unifiedagentprotocol.runtime import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _tool(
    urn: str = "urn:uap:tool:get-weather",
    name: str = "get_weather",
    description: str = "Fetch the current weather for a city.",
) -> Tool:
    return Tool(
        id=urn,
        name=name,
        description=description,
        parameters=[
            Parameter(
                name="city",
                schema=ParameterSchema(type="string"),
                required=True,
                location=ParameterLocation.BODY,
            ),
        ],
        tags=["weather"],
    )


def _agent(
    urn: str = "urn:uap:agent:weather-bot",
    name: str = "WeatherBot",
    description: str = "Provides weather information for cities.",
    tool: Tool | None = None,
) -> Agent:
    return Agent(
        id=urn,
        name=name,
        description=description,
        tools=[tool] if tool is not None else [],
        skills=[
            Skill(
                id="skill.weather",
                name="weather_lookup",
                description="Answer weather questions.",
                tags=["weather"],
            )
        ],
        tags=["weather"],
    )


def _client(registry: InMemoryRegistry) -> TestClient:
    app = create_app(registry, base_url="http://testserver")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_healthz() -> None:
    """`/healthz` returns the canonical liveness shape."""
    client = _client(InMemoryRegistry())
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["uap_version"] == UAP_VERSION
    assert body["sdk_version"] == SDK_VERSION


def test_healthz_uap_version_matches() -> None:
    """The runtime advertises the same UAP version as the core SDK."""
    client = _client(InMemoryRegistry())
    body = client.get("/healthz").json()
    assert body["uap_version"] == UAP_VERSION
    assert body["sdk_version"] == SDK_VERSION


def test_well_known_returns_agent_card_when_single_agent() -> None:
    """With exactly one agent, /.well-known/agent.json is an A2A card."""
    registry = InMemoryRegistry()
    tool = _tool()
    registry.register(tool)
    registry.register(_agent(tool=tool))
    client = _client(registry)

    response = client.get("/.well-known/agent.json")
    assert response.status_code == 200
    card = response.json()
    # Required A2A AgentCard keys.
    for key in ("name", "description", "url", "version", "capabilities", "skills"):
        assert key in card, f"missing A2A key: {key!r} in {card!r}"
    assert isinstance(card["skills"], list)
    assert isinstance(card["capabilities"], dict)


def test_well_known_lists_when_multiple_agents() -> None:
    """With two agents, the index lists their slugs and URLs."""
    registry = InMemoryRegistry()
    registry.register(_agent())
    registry.register(
        _agent(
            urn="urn:uap:agent:billing-bot",
            name="BillingBot",
            description="Handles invoicing.",
        )
    )
    client = _client(registry)

    response = client.get("/.well-known/agent.json")
    assert response.status_code == 200
    payload = response.json()
    assert "agents" in payload
    listed = payload["agents"]
    assert isinstance(listed, list)
    assert len(listed) == 2
    urns = {entry["id"] for entry in listed}
    assert urns == {"urn:uap:agent:weather-bot", "urn:uap:agent:billing-bot"}
    for entry in listed:
        assert entry["url"].startswith("http://testserver/agents/")


def test_tools_endpoint_returns_envelopes() -> None:
    """`/tools` returns UAP envelopes for every registered Tool."""
    registry = InMemoryRegistry()
    registry.register(_tool())
    client = _client(registry)

    response = client.get("/tools")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1

    envelope = payload[0]
    assert envelope["uap_version"] == UAP_VERSION
    assert envelope["kind"] == "tool"
    assert envelope["id"] == "urn:uap:tool:get-weather"
    assert envelope["payload"]["name"] == "get_weather"

    # /tools/{slug} returns the same envelope.
    single = client.get("/tools/get-weather").json()
    assert single == envelope

    # Missing slug -> 404.
    assert client.get("/tools/no-such-tool").status_code == 404


def test_mcp_tools_endpoint() -> None:
    """`/mcp/tools` exposes MCP-shaped dicts with the required keys."""
    registry = InMemoryRegistry()
    registry.register(_tool())
    registry.register(
        _tool(
            urn="urn:uap:tool:open-ticket",
            name="open_ticket",
            description="Open a customer support ticket.",
        )
    )
    client = _client(registry)

    response = client.get("/mcp/tools")
    assert response.status_code == 200
    items = response.json()
    assert isinstance(items, list)
    assert len(items) == 2
    for item in items:
        assert "name" in item
        assert "description" in item
        assert "inputSchema" in item
        assert isinstance(item["inputSchema"], dict)
        assert item["inputSchema"].get("type") == "object"


def test_agent_well_known_per_slug() -> None:
    """Per-agent .well-known card resolves by slug."""
    registry = InMemoryRegistry()
    registry.register(_agent())
    registry.register(
        _agent(
            urn="urn:uap:agent:billing-bot",
            name="BillingBot",
            description="Handles invoicing.",
        )
    )
    client = _client(registry)

    response = client.get("/agents/weather-bot/.well-known/agent.json")
    assert response.status_code == 200
    card = response.json()
    for key in ("name", "description", "version", "capabilities", "skills"):
        assert key in card

    assert (
        client.get("/agents/missing/.well-known/agent.json").status_code == 404
    )


def test_manifests_endpoint_empty() -> None:
    """`/manifests` returns an empty list when nothing is registered."""
    client = _client(InMemoryRegistry())
    response = client.get("/manifests")
    assert response.status_code == 200
    assert response.json() == []
