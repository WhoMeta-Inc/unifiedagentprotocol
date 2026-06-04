# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UIConfig — rendering hints for front-ends."""
from __future__ import annotations

from typing import Optional

from pydantic import Field

from ._base import UAPModel


class UIConfig(UAPModel):
    """Optional UI rendering hints. Front-ends MAY ignore unknown fields."""

    label: str = Field(..., description="Human-readable label.")
    description: Optional[str] = None
    icon: Optional[str] = Field(
        None,
        description='Icon identifier ("mdi:foo") or URL.',
    )
    color: Optional[str] = Field(None, description="CSS color (hex or name).")
    group: Optional[str] = Field(None, description="Logical group for sidebars.")
    order: Optional[int] = Field(None, description="Sort weight (lower first).")
    locale: Optional[str] = Field(None, description="BCP-47 tag for label/description.")
