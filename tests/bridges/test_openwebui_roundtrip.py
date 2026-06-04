# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Round-trip tests for the UAP <-> OpenWebUI tool bridge."""
from __future__ import annotations

from unifiedagentprotocol.bridges.openwebui import from_openwebui, to_openwebui


def test_roundtrip_simple_tool() -> None:
    """A canonical OpenWebUI tool round-trips through the bridge."""
    src = {
        "id": "hello_tool",
        "name": "Hello Tool",
        "description": "Simple greeting tool that returns a personalised greeting.",
        "parameters": {
            "properties": {
                "name": {"type": "string", "description": "Name of the person to greet"}
            },
            "required": ["name"],
        },
        "returns": {
            "type": "object",
            "properties": {
                "greeting": {"type": "string", "description": "Greeting text"}
            },
        },
    }
    tool, _ = from_openwebui(src)
    assert tool.id.startswith("urn:uap:tool:")
    assert tool.description.startswith("Simple greeting tool")
    assert len(tool.parameters) == 1
    p = tool.parameters[0]
    assert p.name == "name"
    assert p.required is True
    assert p.schema_.type == "string"
    assert tool.output is not None

    out, _ = to_openwebui(tool)
    assert out["id"] == "hello_tool"
    assert out["name"] == "Hello Tool"
    assert out["description"].startswith("Simple greeting")
    props = out["parameters"]["properties"]
    assert "name" in props
    assert props["name"]["type"] == "string"
    assert out["parameters"]["required"] == ["name"]
    assert out["returns"]["properties"]["greeting"]["type"] == "string"


def test_unknown_fields_preserved_in_metadata() -> None:
    """Top-level keys we do not model survive via Tool.metadata."""
    src = {
        "id": "custom_tool",
        "name": "Custom",
        "description": "A custom tool",
        "parameters": {"properties": {}, "required": []},
        "custom_field": "preserve_me",
        "extra_dict": {"nested": 1},
    }
    tool, _ = from_openwebui(src)
    assert tool.metadata["custom_field"] == "preserve_me"
    assert tool.metadata["extra_dict"] == {"nested": 1}

    out, _ = to_openwebui(tool)
    assert out["custom_field"] == "preserve_me"
    assert out["extra_dict"] == {"nested": 1}
    # And identity is round-tripped.
    assert out["id"] == "custom_tool"
    assert out["name"] == "Custom"
