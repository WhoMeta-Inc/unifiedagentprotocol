# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip tests for the UAP <-> OpenAI tool / Assistants v2 bridge."""
from __future__ import annotations

from unifiedagentprotocol.bridges.openai import (
    from_openai_assistant,
    from_openai_tool,
    to_openai_assistant,
    to_openai_tool,
)
from unifiedagentprotocol.core import (
    Agent,
    CostHint,
    Parameter,
    ParameterSchema,
    Skill,
    Tool,
    Trigger,
    TriggerType,
)


def _make_basic_tool() -> Tool:
    """Tool with two parameters covering required string+enum and optional int+min."""
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
                ),
                required=True,
            ),
            Parameter(
                name="days",
                schema=ParameterSchema(
                    type="integer",
                    description="Forecast horizon in days.",
                    minimum=1,
                    default=1,
                ),
                required=False,
            ),
        ],
    )


def test_tool_roundtrip_basic() -> None:
    """UAP Tool -> OpenAI function -> UAP Tool preserves the essential fields."""
    original = _make_basic_tool()

    openai_fn, loss_out = to_openai_tool(original)

    # Sanity: wrapped form, correct shape.
    assert openai_fn["type"] == "function"
    body = openai_fn["function"]
    assert body["name"] == "get_weather"
    params = body["parameters"]
    assert params["type"] == "object"
    assert set(params["properties"].keys()) == {"city", "days"}
    assert params["required"] == ["city"]
    assert params["properties"]["city"]["enum"] == ["paris", "berlin", "tokyo"]
    assert params["properties"]["days"]["minimum"] == 1
    assert params["properties"]["days"]["default"] == 1

    restored, loss_in = from_openai_tool(openai_fn)

    assert restored.id == original.id
    assert restored.name == original.name
    assert restored.display_name == original.display_name
    assert restored.description == original.description
    assert restored.version == original.version

    by_name = {p.name: p for p in restored.parameters}
    assert set(by_name.keys()) == {"city", "days"}
    assert by_name["city"].required is True
    assert by_name["city"].schema_.type == "string"
    assert by_name["city"].schema_.enum == ["paris", "berlin", "tokyo"]
    assert by_name["days"].required is False
    assert by_name["days"].schema_.type == "integer"
    assert by_name["days"].schema_.minimum == 1
    assert by_name["days"].schema_.default == 1


def test_tool_accepts_both_wrapped_and_bare() -> None:
    """from_openai_tool must accept both the wrapped and bare function-tool form."""
    wrapped = {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the web.",
            "parameters": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        },
    }
    bare = wrapped["function"]

    t_wrapped, loss_w = from_openai_tool(wrapped)
    t_bare, loss_b = from_openai_tool(bare)

    assert t_wrapped.name == t_bare.name == "search"
    assert t_wrapped.description == t_bare.description == "Search the web."
    assert [p.name for p in t_wrapped.parameters] == ["q"]
    assert [p.name for p in t_bare.parameters] == ["q"]
    assert t_wrapped.parameters[0].required is True
    assert t_bare.parameters[0].required is True
    # Synthetic URNs are stable across the two forms.
    assert t_wrapped.id == t_bare.id


def test_assistant_roundtrip_preserves_urn() -> None:
    """metadata.uap_urn must survive a full Agent -> Assistant -> Agent round trip."""
    agent = Agent(
        id="urn:uap:agent:weather-bot",
        name="WeatherBot",
        description="Answers weather questions.",
        version="2.0.0",
        tools=[_make_basic_tool()],
        skills=[
            Skill(
                id="skill-1",
                name="forecast",
                description="Provide a multi-day forecast.",
            ),
        ],
        metadata={"openai_model": "gpt-4o-mini"},
    )

    assistant, loss_out = to_openai_assistant(agent)

    assert assistant["metadata"]["uap_urn"] == "urn:uap:agent:weather-bot"
    assert assistant["metadata"]["uap_version"] == "2.0.0"
    # The configured model carried through.
    assert assistant["model"] == "gpt-4o-mini"
    assert assistant["name"] == "WeatherBot"
    assert assistant["tools"][0]["type"] == "function"
    assert assistant["tools"][0]["function"]["name"] == "get_weather"

    restored, loss_in = from_openai_assistant(assistant)

    assert restored.id == "urn:uap:agent:weather-bot"
    assert restored.version == "2.0.0"
    assert restored.name == "WeatherBot"
    assert len(restored.tools) == 1
    assert isinstance(restored.tools[0], Tool)
    assert restored.tools[0].id == "urn:uap:tool:get-weather"
    # Round-tripped OpenAI knobs land back in metadata.
    assert restored.metadata.get("openai_model") == "gpt-4o-mini"


def test_assistant_with_skills_to_instructions() -> None:
    """With no explicit instructions, skills should be folded into instructions."""
    agent = Agent(
        id="urn:uap:agent:helper",
        name="Helper",
        description="A friendly helper.",
        skills=[
            Skill(
                id="s1",
                name="summarize",
                description="Summarize long text.",
                examples=["Summarize this paragraph."],
            ),
            Skill(
                id="s2",
                name="translate",
                description="Translate text between languages.",
            ),
        ],
    )

    assistant, _ = to_openai_assistant(agent)
    instructions = assistant["instructions"]

    assert "A friendly helper." in instructions
    assert "summarize" in instructions
    assert "Summarize long text." in instructions
    assert "translate" in instructions
    assert "Translate text between languages." in instructions
    assert "Summarize this paragraph." in instructions


def test_assistant_with_explicit_instructions_overrides_skills() -> None:
    """An explicit instructions hint in metadata wins over the skills concatenation."""
    agent = Agent(
        id="urn:uap:agent:helper2",
        name="Helper2",
        description="Description text.",
        skills=[
            Skill(id="s1", name="summarize", description="Summarize long text."),
        ],
        metadata={"openai_instructions": "Be terse."},
    )
    assistant, _ = to_openai_assistant(agent)
    assert assistant["instructions"] == "Be terse."


def test_losses_recorded_for_unsupported() -> None:
    """A Tool carrying a cron trigger + cost must record those as losses."""
    tool = Tool(
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
        triggers=[Trigger(type=TriggerType.CRON, cron="0 2 * * *")],
        cost=CostHint(currency="USD", per_call_usd=0.05),
    )

    _, loss = to_openai_tool(tool)

    assert "triggers" in loss.dropped_fields
    assert "cost" in loss.dropped_fields
    # capabilities and compliance always vanish through OpenAI's surface.
    assert "capabilities" in loss.dropped_fields
    assert "compliance" in loss.dropped_fields
    assert loss.is_lossy()
