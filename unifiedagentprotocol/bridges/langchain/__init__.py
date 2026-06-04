# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and LangChain tool dicts.

LangChain itself is not imported; this bridge operates on the canonical
serialized dict that LangChain's tools surface::

    {
      "name": "...",
      "description": "...",
      "args_schema": {
        "<param>": {
          "type": "string",
          "description": "...",
          "required": true,
          "default": null,
          "enum": [...]
        },
        ...
      },
      "return_schema": {"type": "object", "properties": {...}}
    }

The bridge produces a single UAP :class:`Tool`. All inputs default to
``location=body``. Unknown top-level keys are preserved in
``Tool.metadata`` for round-trip fidelity.
"""
from __future__ import annotations

from .to_langchain import to_langchain, tool_to_langchain
from .from_langchain import from_langchain, tool_from_langchain

__all__ = [
    "to_langchain",
    "from_langchain",
    "tool_to_langchain",
    "tool_from_langchain",
]
