# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip tests for the UAP <-> Anthropic Tool Use bridge."""
from __future__ import annotations

import re

import pytest

from unifiedagentprotocol.bridges.anthropic import (
    from_anthropic,
    to_anthropic,
    tool_from_anthropic,
    tool_to_anthropic,
)
from unifiedagentprotocol.core import (
    Agent,
    Capabilities,
    Parameter,
    ParameterSchema,
    Tool,
)

URN_RE = re.compile(r"^urn:uap:tool:[a-z0-9][a-z0-9._-]*$")


def _make_basic_tool() -> Tool:
    """Tool with two parameters covering required string and optional integer.

    The URN slug intentionally matches what ``_slugify(name)`` produces, so the
    round-trip URN is bit-identical. Capabilities default to non-approval to
    keep the description marker-free in the basic case.
    """
    return Tool(
        id="urn:uap:tool:get_weather",
        name="get_weather",
        description="Look up the current weather for a city.",
        version="1.2.0",
        parameters=[
            Parameter(
                name="city",
                schema=ParameterSchema(
                    type="string",
                    description="Target city.",
                ),
                required=True,
            ),
            Parameter(
                name="days",
                schema=ParameterSchema(
                    type="integer",
                    description="Forecast horizon in days.",
                    minimum=1,
                ),
                required=False,
            ),
        ],
        capabilities=Capabilities(requires_human_approval=False),
    )


def test_basic_roundtrip() -> None:
    """A UAP Tool with two parameters round-trips through Anthropic tool-use."""
    original = _make_basic_tool()

    anth, loss_out = to_anthropic(original)

    # Shape: name, description, input_schema with proper JSON-Schema object.
    assert anth["name"] == "get_weather"
    assert anth["description"] == "Look up the current weather for a city."
    schema = anth["input_schema"]
    assert schema["type"] == "object"
    assert set(schema["properties"].keys()) == {"city", "days"}
    assert schema["required"] == ["city"]
    assert schema["properties"]["city"]["type"] == "string"
    assert schema["properties"]["days"]["type"] == "integer"
    assert schema["properties"]["days"]["minimum"] == 1

    restored, loss_in = from_anthropic(anth)

    assert restored.name == original.name
    assert restored.description == original.description
    # URN was synthesized from the name; the name slugifies identically.
    assert restored.id == original.id

    by_name = {p.name: p for p in restored.parameters}
    assert set(by_name.keys()) == {"city", "days"}
    assert by_name["city"].required is True
    assert by_name["city"].schema_.type == "string"
    assert by_name["days"].required is False
    assert by_name["days"].schema_.type == "integer"
    assert by_name["days"].schema_.minimum == 1


def test_requires_human_approval_carried_via_description() -> None:
    """The requires_human_approval capability survives the round trip."""
    tool = Tool(
        id="urn:uap:tool:delete-account",
        name="delete_account",
        description="Permanently delete a user account.",
        parameters=[
            Parameter(
                name="user_id",
                schema=ParameterSchema(type="string"),
                required=True,
            ),
        ],
        capabilities=Capabilities(requires_human_approval=True),
    )

    anth, loss_out = to_anthropic(tool)

    assert anth["description"].startswith("[REQUIRES HUMAN APPROVAL] ")
    assert anth["description"].endswith("Permanently delete a user account.")
    assert "capabilities.requires_human_approval" in loss_out.coerced_fields

    restored, loss_in = from_anthropic(anth)

    assert restored.description == "Permanently delete a user account."
    assert restored.capabilities.requires_human_approval is True
    assert "capabilities.requires_human_approval" in loss_in.coerced_fields


def test_agent_rejected() -> None:
    """Anthropic has no agent-level concept; to_anthropic must reject Agent."""
    agent = Agent(
        id="urn:uap:agent:weather-bot",
        name="WeatherBot",
        description="Answers weather questions.",
    )
    with pytest.raises(ValueError) as excinfo:
        to_anthropic(agent)
    assert "agent" in str(excinfo.value).lower()


def test_synthesize_urn_on_import() -> None:
    """An Anthropic input with no URN yields a valid synthesized URN."""
    anth = {
        "name": "search_docs",
        "description": "Search internal documentation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    }

    restored, loss = tool_from_anthropic(anth)

    assert URN_RE.match(restored.id), restored.id
    assert restored.id == "urn:uap:tool:search_docs"
    assert restored.name == "search_docs"
    assert restored.parameters[0].name == "query"
    assert restored.parameters[0].required is True
    assert any("Synthesized URN" in note for note in loss.notes)


def test_tool_to_anthropic_records_envelope_losses() -> None:
    """Helper coverage: capabilities and compliance are always recorded as dropped."""
    tool = _make_basic_tool()
    _, loss = tool_to_anthropic(tool)
    assert "capabilities" in loss.dropped_fields
    assert "compliance" in loss.dropped_fields
