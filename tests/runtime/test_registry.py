# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Unit tests for the reference registry backends.

Covers both :class:`InMemoryRegistry` and :class:`FilesystemRegistry`,
including search semantics, kind filters, and on-disk persistence
across instance lifetimes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from unifiedagentprotocol.core import (
    Agent,
    Kind,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    Tool,
)
from unifiedagentprotocol.registry_impl import (
    FilesystemRegistry,
    InMemoryRegistry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _weather_tool() -> Tool:
    return Tool(
        id="urn:uap:tool:get-weather",
        name="get_weather",
        display_name="Get Weather",
        description="Fetch the current weather for a city.",
        parameters=[
            Parameter(
                name="city",
                schema=ParameterSchema(type="string", min_length=1),
                required=True,
                location=ParameterLocation.BODY,
            ),
        ],
        tags=["weather", "public"],
    )


def _ticket_tool() -> Tool:
    return Tool(
        id="urn:uap:tool:open-ticket",
        name="open_ticket",
        display_name="Open Support Ticket",
        description="Open a customer support ticket.",
        tags=["support", "internal"],
    )


def _weather_agent(tool: Tool) -> Agent:
    return Agent(
        id="urn:uap:agent:weather-bot",
        name="WeatherBot",
        display_name="Weather Bot",
        description="An agent specialised in weather queries.",
        tools=[tool],
        tags=["weather"],
    )


# ---------------------------------------------------------------------------
# In-memory backend
# ---------------------------------------------------------------------------


def test_in_memory_register_get() -> None:
    """Full register / get / list / delete cycle for InMemoryRegistry."""
    registry = InMemoryRegistry()
    tool = _weather_tool()
    agent = _weather_agent(tool)

    registry.register(tool)
    registry.register(agent)

    fetched_tool = registry.get(tool.id)
    fetched_agent = registry.get(agent.id)

    assert fetched_tool is tool
    assert fetched_agent is agent
    assert registry.get("urn:uap:tool:does-not-exist") is None

    listed = registry.list()
    assert {o.id for o in listed} == {tool.id, agent.id}

    assert registry.delete(tool.id) is True
    assert registry.get(tool.id) is None
    assert registry.delete(tool.id) is False
    assert {o.id for o in registry.list()} == {agent.id}


def test_in_memory_search() -> None:
    """Search matches name / description / tags case-insensitively."""
    registry = InMemoryRegistry()
    weather = _weather_tool()
    ticket = _ticket_tool()
    registry.register(weather)
    registry.register(ticket)

    # Substring against description, case-insensitive.
    results = registry.search("WEATHER")
    assert weather in results
    assert ticket not in results

    # Substring against name.
    by_name = registry.search("open_ticket")
    assert ticket in by_name

    # Substring against display_name.
    by_display = registry.search("support ticket")
    assert ticket in by_display

    # Tag filter via list().
    by_tag = registry.list(tag="weather")
    assert {o.id for o in by_tag} == {weather.id}

    # Kind narrowing in search.
    only_tools = registry.search("ticket", kind=Kind.TOOL)
    assert ticket in only_tools


def test_filesystem_persistence(tmp_path: Path) -> None:
    """Records written via one instance are visible to a fresh one."""
    root = tmp_path / "store"
    first = FilesystemRegistry(root)
    tool = _weather_tool()
    agent = _weather_agent(tool)

    first.register(tool)
    first.register(agent)

    # Drop the first instance; rehydrate from disk.
    del first
    second = FilesystemRegistry(root)

    fetched_tool = second.get(tool.id)
    fetched_agent = second.get(agent.id)
    assert fetched_tool is not None
    assert fetched_agent is not None
    assert fetched_tool.name == "get_weather"
    assert fetched_agent.name == "WeatherBot"

    # Verify the canonical layout: {root}/{kind}/{slug}.json
    tool_path = root / "tool" / "get-weather.json"
    agent_path = root / "agent" / "weather-bot.json"
    assert tool_path.is_file()
    assert agent_path.is_file()

    # Delete via the second instance and confirm the file is gone.
    assert second.delete(tool.id) is True
    assert not tool_path.exists()
    assert second.get(tool.id) is None


def test_kind_filter() -> None:
    """``list(kind=...)`` returns only records of the requested kind."""
    registry = InMemoryRegistry()
    weather = _weather_tool()
    ticket = _ticket_tool()
    agent = _weather_agent(weather)

    registry.register(weather)
    registry.register(ticket)
    registry.register(agent)

    only_tools = registry.list(kind=Kind.TOOL)
    only_agents = registry.list(kind=Kind.AGENT)

    assert {o.id for o in only_tools} == {weather.id, ticket.id}
    assert {o.id for o in only_agents} == {agent.id}

    # Tag + kind interaction.
    weather_tools = registry.list(kind=Kind.TOOL, tag="weather")
    assert {o.id for o in weather_tools} == {weather.id}


def test_filesystem_kind_filter(tmp_path: Path) -> None:
    """Sanity-check kind filter on the filesystem backend too."""
    registry = FilesystemRegistry(tmp_path)
    weather = _weather_tool()
    ticket = _ticket_tool()
    agent = _weather_agent(weather)

    registry.register(weather)
    registry.register(ticket)
    registry.register(agent)

    only_tools = registry.list(kind=Kind.TOOL)
    only_agents = registry.list(kind=Kind.AGENT)

    assert {o.id for o in only_tools} == {weather.id, ticket.id}
    assert {o.id for o in only_agents} == {agent.id}


def test_filesystem_search(tmp_path: Path) -> None:
    """Filesystem search honours the same substring semantics."""
    registry = FilesystemRegistry(tmp_path)
    registry.register(_weather_tool())
    registry.register(_ticket_tool())

    hits = registry.search("weather")
    assert {o.id for o in hits} == {"urn:uap:tool:get-weather"}

    # Limit cap.
    limited = registry.search("", limit=1)  # empty needle matches every record
    assert len(limited) == 1
