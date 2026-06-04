# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Example 2 — Bridge one UAP Agent into many vendor formats.

Run from the repo root:

    PYTHONPATH=. python examples/02_bridge_to_many_formats.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from importlib import import_module

_demo = import_module("01_define_tool_and_agent")
agent, tool = _demo.agent, _demo.tool

from unifiedagentprotocol.bridges.a2a import to_a2a
from unifiedagentprotocol.bridges.anthropic import to_anthropic
from unifiedagentprotocol.bridges.gemini import to_gemini
from unifiedagentprotocol.bridges.mcp import to_mcp
from unifiedagentprotocol.bridges.openai import to_openai
from unifiedagentprotocol.bridges.openapi import to_openapi


def emit(name: str, obj, loss) -> None:
    print(f"\n=== {name} ===")
    print(json.dumps(obj, indent=2))
    if loss.is_lossy():
        print(f"-- LossInfo: {loss.model_dump()}")


if __name__ == "__main__":
    emit("MCP (agent)", *to_mcp(agent))
    emit("A2A AgentCard", *to_a2a(agent))
    emit("OpenAPI 3 (agent)", *to_openapi(agent))
    emit("OpenAI function tool", *to_openai(tool))
    emit("Anthropic tool", *to_anthropic(tool))
    emit("Gemini function decl.", *to_gemini(tool))
