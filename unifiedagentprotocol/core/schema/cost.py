# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""CostHint — orchestrator-readable economics & latency estimates."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from ._base import UAPModel


class CostHint(UAPModel):
    """Best-effort cost & latency estimates per invocation.

    These are *hints*. Concrete billing is the runtime's responsibility.
    Use them for routing, batching and budgeting decisions.
    """

    currency: str = Field("USD", min_length=3, max_length=3)
    per_call_usd: Optional[float] = Field(None, ge=0)
    tokens_in_estimate: Optional[int] = Field(None, ge=0)
    tokens_out_estimate: Optional[int] = Field(None, ge=0)
    latency_ms_p50: Optional[int] = Field(None, ge=0)
    latency_ms_p99: Optional[int] = Field(None, ge=0)
