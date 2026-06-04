# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""LossInfo — explicit declaration of fields lost during bridge conversion.

A bridge MUST return a LossInfo alongside its converted payload whenever
the source format cannot represent a field present in the target (or vice
versa). Silent data loss is forbidden by the spec.
"""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field


class LossInfo(BaseModel):
    """Information about lossy aspects of a bridge conversion."""

    model_config = ConfigDict(extra="forbid")

    dropped_fields: List[str] = Field(
        default_factory=list,
        description="Dot-paths of fields present in source but absent in target.",
    )
    coerced_fields: List[str] = Field(
        default_factory=list,
        description="Dot-paths of fields whose value was approximated.",
    )
    notes: List[str] = Field(
        default_factory=list,
        description="Free-form human-readable explanations.",
    )

    def is_lossy(self) -> bool:
        return bool(self.dropped_fields or self.coerced_fields)

    def merge(self, other: "LossInfo") -> "LossInfo":
        return LossInfo(
            dropped_fields=[*self.dropped_fields, *other.dropped_fields],
            coerced_fields=[*self.coerced_fields, *other.coerced_fields],
            notes=[*self.notes, *other.notes],
        )
