# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP runtime — optional FastAPI adapter.

Importing from this package requires the ``[runtime]`` extra:

    pip install unified-agent-protocol[runtime]
"""
from .directory import DirectoryMatch, match_agents
from .server import create_app
from .task_envelope import AgentTaskPayload, TaskEnvelope

__all__ = [
    "AgentTaskPayload",
    "DirectoryMatch",
    "TaskEnvelope",
    "create_app",
    "match_agents",
]
