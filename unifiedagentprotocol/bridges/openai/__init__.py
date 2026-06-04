# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and OpenAI's tool / Assistants v2 format.

OpenAI surfaces two related artifacts:

* **Function tools** — the ``{"type": "function", "function": {...}}`` schema
  used in Chat Completions, Responses and the Assistants ``tools`` array.
* **Assistants v2** — a top-level object carrying ``model``, ``instructions``,
  a ``tools`` list and ``metadata``.

Public entry points::

    to_openai_tool(tool)             -> (function_tool: dict, LossInfo)
    from_openai_tool(fn)             -> (Tool, LossInfo)
    to_openai_assistant(agent)       -> (assistant: dict, LossInfo)
    from_openai_assistant(assistant) -> (Agent, LossInfo)
    to_openai(obj)                   -> (dict, LossInfo)            # dispatcher
    from_openai(obj)                 -> (Tool | Agent, LossInfo)    # autodetect

Round-trip stability is preserved by smuggling the UAP URN through
``metadata.uap_urn`` on the Assistant and through the tool ``name``.
"""
from __future__ import annotations

from .to_openai import (
    tool_to_openai_function as to_openai_tool,
    agent_to_openai_assistant as to_openai_assistant,
    to_openai,
)
from .from_openai import (
    tool_from_openai_function as from_openai_tool,
    agent_from_openai_assistant as from_openai_assistant,
    from_openai,
)

__all__ = [
    "to_openai_tool",
    "from_openai_tool",
    "to_openai_assistant",
    "from_openai_assistant",
    "to_openai",
    "from_openai",
]
