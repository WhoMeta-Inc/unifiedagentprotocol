# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Capabilities — behavioural metadata for orchestrators and policy engines."""
from __future__ import annotations

from enum import Enum

from ._base import UAPModel


class SideEffects(str, Enum):
    NONE = "none"
    READ_ONLY = "read_only"
    WRITES = "writes"
    DESTRUCTIVE = "destructive"


class Capabilities(UAPModel):
    """Behavioural properties used by orchestrators, policy engines, and UIs.

    Defaults reflect the safest assumption: not idempotent, writes state,
    requires human approval. Tool authors MUST relax these explicitly.
    """

    idempotent: bool = False
    side_effects: SideEffects = SideEffects.WRITES
    deterministic: bool = False
    requires_human_approval: bool = True
    long_running: bool = False
    supports_streaming: bool = False
    supports_cancellation: bool = False
    max_concurrency: int = 1
