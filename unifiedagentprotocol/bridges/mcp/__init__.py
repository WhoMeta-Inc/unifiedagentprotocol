# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP <-> MCP (Model Context Protocol) bridge.

This bridge maps UAP ``Tool`` and ``Agent`` objects to and from
Model Context Protocol descriptors. MCP models a server exposing
``tools``, ``resources``, and ``prompts``; each MCP Tool has a
JSON-Schema ``inputSchema``.

UAP's enterprise envelope (auth, capabilities, compliance, cost) is
carried inside MCP's ``annotations`` map under ``x-uap-*`` keys, so
round-tripping is lossless for any UAP object that uses only
MCP-representable fields. Fields that cannot be represented (cron
triggers, mTLS auth, non-http/stdio transports, data residency)
are reported through :class:`LossInfo`.

Two convenience wrappers (:func:`to_mcp` / :func:`from_mcp`) dispatch
on the input type, while :func:`to_mcp_tool` and :func:`from_mcp_tool`
are direct aliases for the tool-only variants.
"""
from __future__ import annotations

from .from_mcp import agent_from_mcp, from_mcp, from_mcp_tool, tool_from_mcp
from .to_mcp import agent_to_mcp, to_mcp, to_mcp_tool, tool_to_mcp

__all__ = [
    "to_mcp",
    "from_mcp",
    "to_mcp_tool",
    "from_mcp_tool",
    "tool_to_mcp",
    "tool_from_mcp",
    "agent_to_mcp",
    "agent_from_mcp",
]
