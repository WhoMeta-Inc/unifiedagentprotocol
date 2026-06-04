# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Shared base configuration for UAP schema models."""
from __future__ import annotations

import re
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict


URN_RE = re.compile(r"^urn:uap:(agent|tool|manifest):[a-z0-9][a-z0-9._-]*$")


class UAPModel(BaseModel):
    """Common configuration: forbid silent unknowns, allow x-* extensions."""

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        str_strip_whitespace=True,
        validate_assignment=True,
        ser_json_inf_nan="constants",
    )

    def to_wire(self) -> Dict[str, Any]:
        """Serialize to the canonical wire dict (drops None, sorts keys)."""
        return self.model_dump(mode="json", exclude_none=True, by_alias=True)


def validate_urn(value: str, kind: str) -> str:
    if not URN_RE.match(value):
        raise ValueError(
            f"Invalid URN '{value}'. Expected pattern urn:uap:{kind}:<slug>"
        )
    parts = value.split(":")
    if parts[2] != kind:
        raise ValueError(f"URN kind mismatch: expected {kind}, got {parts[2]}")
    return value
