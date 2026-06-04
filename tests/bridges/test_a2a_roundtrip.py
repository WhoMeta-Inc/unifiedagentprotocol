# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip and shape tests for the UAP <-> A2A AgentCard bridge."""
from __future__ import annotations

import pytest

from unifiedagentprotocol.bridges.a2a import from_a2a, to_a2a
from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    AuthType,
    Capabilities,
    Endpoint,
    Skill,
    Tool,
    Transport,
    Trigger,
    TriggerType,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_agent(**overrides) -> Agent:
    """Build a moderately rich Agent suitable for round-trip tests."""
    defaults = dict(
        id="urn:uap:agent:weather-bot",
        name="weather_bot",
        display_name="Weather Bot",
        description="Surfaces public weather APIs.",
        version="1.2.3",
        skills=[
            Skill(
                id="forecast",
                name="forecast",
                description="Multi-day weather forecast.",
                input_modes=["text"],
                output_modes=["text"],
                examples=["What's the weather in Berlin tomorrow?"],
                tags=["weather", "forecast"],
            )
        ],
        endpoints=[Endpoint(transport=Transport.HTTP, url="https://api.weather.example/v1")],
        auth=AuthConfig(type=AuthType.BEARER, secret_ref="vault://kv/data/weather#token"),
        capabilities=Capabilities(supports_streaming=True),
        publisher="Acme",
        homepage="https://acme.example",
    )
    defaults.update(overrides)
    return Agent(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_agent_card_shape():
    """The exported AgentCard has the spec-required top-level keys."""
    agent = _make_agent()
    card, loss = to_a2a(agent)

    required_keys = {
        "name",
        "description",
        "url",
        "version",
        "capabilities",
        "authentication",
        "defaultInputModes",
        "defaultOutputModes",
        "skills",
    }
    missing = required_keys - card.keys()
    assert not missing, f"AgentCard missing keys: {missing}"

    # Required nested shapes
    assert isinstance(card["capabilities"], dict)
    assert set(card["capabilities"]) == {
        "streaming",
        "pushNotifications",
        "stateTransitionHistory",
    }
    assert isinstance(card["authentication"], dict)
    assert isinstance(card["authentication"]["schemes"], list)
    assert isinstance(card["skills"], list)
    assert isinstance(card["defaultInputModes"], list)
    assert isinstance(card["defaultOutputModes"], list)


def test_roundtrip_preserves_urn_via_metadata():
    """An agent with a URN survives ``from_a2a(to_a2a(a)[0])``."""
    agent = _make_agent()
    card, _ = to_a2a(agent)
    assert card["metadata"]["uap_urn"] == agent.id

    restored, _ = from_a2a(card)
    assert restored.id == agent.id
    assert restored.name == agent.name
    assert restored.version == agent.version
    assert restored.description == agent.description
    assert len(restored.skills) == 1
    assert restored.skills[0].id == "forecast"
    assert restored.endpoints and restored.endpoints[0].url == (
        "https://api.weather.example/v1"
    )
    assert restored.capabilities.supports_streaming is True
    assert restored.auth is not None
    assert restored.auth.type == AuthType.BEARER
    assert restored.publisher == "Acme"
    assert restored.homepage == "https://acme.example"


def test_tool_rejected():
    """Calling ``to_a2a`` on a :class:`Tool` raises :class:`ValueError`."""
    tool = Tool(
        id="urn:uap:tool:get-weather",
        name="get_weather",
        description="Fetch a forecast.",
    )
    with pytest.raises(ValueError):
        to_a2a(tool)


def test_capability_mapping():
    """``Capabilities.supports_streaming`` maps to ``capabilities.streaming``."""
    streaming_agent = _make_agent(capabilities=Capabilities(supports_streaming=True))
    card, _ = to_a2a(streaming_agent)
    assert card["capabilities"]["streaming"] is True

    non_streaming = _make_agent(capabilities=Capabilities(supports_streaming=False))
    card2, _ = to_a2a(non_streaming)
    assert card2["capabilities"]["streaming"] is False

    # ``long_running`` -> ``stateTransitionHistory``
    long_running = _make_agent(
        capabilities=Capabilities(supports_streaming=False, long_running=True)
    )
    card3, _ = to_a2a(long_running)
    assert card3["capabilities"]["stateTransitionHistory"] is True

    # ``pushNotifications`` -> any tool webhook trigger
    webhook_tool = Tool(
        id="urn:uap:tool:incoming",
        name="incoming",
        description="Webhook ingress.",
        triggers=[Trigger(type=TriggerType.WEBHOOK, webhook_path="/hooks/x")],
    )
    push_agent = _make_agent(tools=[webhook_tool])
    card4, _ = to_a2a(push_agent)
    assert card4["capabilities"]["pushNotifications"] is True


def test_unsupported_auth_recorded_in_loss():
    """An Agent with mTLS auth records a loss and degrades to 'bearer'."""
    agent = _make_agent(
        auth=AuthConfig(type=AuthType.MTLS, secret_ref="vault://kv/data/mtls#cert"),
    )
    card, loss = to_a2a(agent)
    assert card["authentication"]["schemes"] == ["bearer"]
    assert "auth.type" in loss.coerced_fields
    assert any("mtls" in n for n in loss.notes)


def test_synthesize_urn_when_missing():
    """An AgentCard without ``metadata.uap_urn`` yields a valid synthesized URN."""
    card = {
        "name": "Spaced Name!!",
        "description": "demo",
        "url": "https://example.com",
        "version": "0.1.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "authentication": {"schemes": ["none"]},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [],
    }
    agent, loss = from_a2a(card)
    assert agent.id.startswith("urn:uap:agent:")
    # Slugified: lowercased, non-[a-z0-9._-] -> "-"
    assert agent.id == "urn:uap:agent:spaced-name"
    # And the URN validator on Agent.id accepts it (no exception above)
    assert any("synthesized" in n.lower() for n in loss.notes)
