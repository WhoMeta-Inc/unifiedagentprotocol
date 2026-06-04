# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and OpenWebUI tool definitions.

OpenWebUI represents a tool as a JSON document::

    {
      "id": "weather_tool",
      "name": "Weather Tool",
      "description": "...",
      "parameters": {"properties": {...}, "required": [...]},
      "returns": {"type": "object", "properties": {...}},
      "trigger": {...},
      "ui": {...}
    }

The bridge maps this to a single UAP :class:`Tool`. Unknown top-level
fields are preserved verbatim in ``Tool.metadata`` so round-trips are
lossless on the OpenWebUI side.
"""
from __future__ import annotations

from .to_openwebui import to_openwebui, tool_to_openwebui
from .from_openwebui import from_openwebui, tool_from_openwebui

__all__ = [
    "to_openwebui",
    "from_openwebui",
    "tool_to_openwebui",
    "tool_from_openwebui",
]
