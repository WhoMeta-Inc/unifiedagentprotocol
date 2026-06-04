# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip tests for the UAP <-> LangChain tool dict bridge."""
from __future__ import annotations

from unifiedagentprotocol.bridges.langchain import from_langchain, to_langchain
from unifiedagentprotocol.core import ParameterLocation


def test_roundtrip_simple_tool() -> None:
    """A simple LangChain tool dict survives a round trip."""
    src = {
        "name": "hello_tool",
        "description": "Greets a user by name.",
        "args_schema": {
            "name": {
                "type": "string",
                "description": "Name of the person to greet",
                "required": True,
            }
        },
        "return_schema": {
            "type": "object",
            "properties": {"greeting": {"type": "string"}},
        },
    }
    tool, _ = from_langchain(src)
    assert tool.id.startswith("urn:uap:tool:")
    assert tool.description == "Greets a user by name."
    assert len(tool.parameters) == 1
    p = tool.parameters[0]
    assert p.name == "name"
    assert p.required is True
    assert p.location is ParameterLocation.BODY
    assert p.schema_.type == "string"
    assert tool.output is not None

    out, _ = to_langchain(tool)
    assert out["name"] == "hello_tool"
    assert out["description"] == "Greets a user by name."
    assert "name" in out["args_schema"]
    entry = out["args_schema"]["name"]
    assert entry["type"] == "string"
    assert entry["required"] is True
    assert out["return_schema"]["properties"]["greeting"]["type"] == "string"


def test_enum_and_default_survive() -> None:
    """Enum and default fields survive the LangChain round trip."""
    src = {
        "name": "pick_color",
        "description": "Pick a color from a fixed palette.",
        "args_schema": {
            "color": {
                "type": "string",
                "description": "Palette colour",
                "enum": ["red", "green", "blue"],
                "default": "red",
                "required": False,
            }
        },
    }
    tool, _ = from_langchain(src)
    p = tool.parameters[0]
    assert p.schema_.enum == ["red", "green", "blue"]
    assert p.schema_.default == "red"
    assert p.required is False

    out, _ = to_langchain(tool)
    entry = out["args_schema"]["color"]
    assert entry["enum"] == ["red", "green", "blue"]
    assert entry["default"] == "red"
    assert entry["required"] is False
