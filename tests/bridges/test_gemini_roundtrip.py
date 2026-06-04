# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip tests for the UAP <-> Google Gemini function-declaration bridge."""
from __future__ import annotations

from unifiedagentprotocol.bridges.gemini import (
    from_gemini,
    to_gemini,
    tool_from_gemini,
    tool_to_gemini,
)
from unifiedagentprotocol.core import (
    Parameter,
    ParameterSchema,
    Tool,
)


def _make_basic_tool() -> Tool:
    """The URN slug matches what ``_slugify(name)`` produces, so the
    round-trip URN is bit-identical."""
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
    )


def test_uppercase_types_emitted() -> None:
    """Gemini OpenAPI convention: all schema 'type' values are uppercase."""
    tool = _make_basic_tool()
    decl, _ = to_gemini(tool)

    params = decl["parameters"]
    assert params["type"] == "OBJECT"
    assert params["properties"]["city"]["type"] == "STRING"
    assert params["properties"]["days"]["type"] == "INTEGER"


def test_basic_roundtrip() -> None:
    """A UAP Tool with two parameters round-trips through Gemini."""
    original = _make_basic_tool()

    decl, loss_out = to_gemini(original)

    assert decl["name"] == "get_weather"
    assert decl["description"] == "Look up the current weather for a city."

    restored, loss_in = from_gemini(decl)

    assert restored.name == original.name
    assert restored.description == original.description
    # Slug derivation re-yields the same URN for this name.
    assert restored.id == original.id

    by_name = {p.name: p for p in restored.parameters}
    assert set(by_name.keys()) == {"city", "days"}

    # Types are restored to lowercase JSON-Schema values.
    assert by_name["city"].schema_.type == "string"
    assert by_name["days"].schema_.type == "integer"
    assert by_name["city"].required is True
    assert by_name["days"].required is False
    assert by_name["days"].schema_.minimum == 1
    # Descriptions on nested schemas survive the conversion.
    assert by_name["city"].schema_.description == "Target city."


def test_unsupported_type_records_loss() -> None:
    """A UAP parameter with schema.format='email' is recorded as coerced."""
    tool = Tool(
        id="urn:uap:tool:send-mail",
        name="send_mail",
        description="Send an email.",
        parameters=[
            Parameter(
                name="to",
                schema=ParameterSchema(type="string", format="email"),
                required=True,
            ),
        ],
    )

    _, loss = to_gemini(tool)

    # The format field is preserved as a hint but recorded as coerced because
    # Gemini does not standardise 'format' values.
    assert any(
        path.endswith(".format") for path in loss.coerced_fields
    ), loss.coerced_fields
    assert loss.is_lossy()


def test_envelope_dropped_fields_recorded() -> None:
    """capabilities and compliance are always recorded as dropped."""
    _, loss = tool_to_gemini(_make_basic_tool())
    assert "capabilities" in loss.dropped_fields
    assert "compliance" in loss.dropped_fields


def test_from_gemini_synthesizes_urn() -> None:
    """A Gemini declaration with no URN yields a valid synthesized URN."""
    decl = {
        "name": "search_docs",
        "description": "Search the docs.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING"},
            },
            "required": ["query"],
        },
    }

    restored, loss = tool_from_gemini(decl)
    assert restored.id == "urn:uap:tool:search_docs"
    assert restored.parameters[0].schema_.type == "string"
    assert any("Synthesized URN" in note for note in loss.notes)
