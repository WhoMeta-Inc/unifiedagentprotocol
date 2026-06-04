# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and Anthropic Tool Use.

Anthropic's tool-use format (https://docs.claude.com/en/docs/build-with-claude/tool-use)
describes individual callable tools with ``name``, ``description``, and a JSON
Schema ``input_schema``. It has no agent-level concept; ``to_anthropic`` rejects
:class:`~unifiedagentprotocol.core.Agent` inputs.

The two public entry-points are::

    to_anthropic(obj)             -> (tool_dict: dict, LossInfo)
    from_anthropic(tool_dict)     -> (Tool, LossInfo)

Round-trip stability for the ``requires_human_approval`` capability flag is
preserved by prepending ``[REQUIRES HUMAN APPROVAL] `` to the tool description
and stripping the marker on import.
"""
from __future__ import annotations

from .to_anthropic import to_anthropic, tool_to_anthropic
from .from_anthropic import from_anthropic, tool_from_anthropic

__all__ = [
    "to_anthropic",
    "from_anthropic",
    "tool_to_anthropic",
    "tool_from_anthropic",
]
