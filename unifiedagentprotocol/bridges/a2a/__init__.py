# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and Google's Agent2Agent (A2A) protocol.

The A2A protocol surfaces an agent through an ``AgentCard`` document. A2A is
agent-level only: standalone tool definitions cannot be expressed and are
rejected by ``to_a2a``.

The two public entry-points are:

    to_a2a(obj)        -> (agent_card: dict, LossInfo)
    from_a2a(card)     -> (Agent, LossInfo)

Round-trip stability is preserved by smuggling the UAP URN through
``AgentCard.metadata.uap_urn`` and tool URNs through
``AgentCard.metadata.uap_tools``.
"""
from __future__ import annotations

from .to_a2a import agent_to_a2a, to_a2a
from .from_a2a import agent_from_a2a, from_a2a

__all__ = [
    "to_a2a",
    "from_a2a",
    "agent_to_a2a",
    "agent_from_a2a",
]
