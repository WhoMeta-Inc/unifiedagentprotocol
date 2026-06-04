# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Tool — an executable capability."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from ._base import UAPModel, validate_urn
from .auth import AuthConfig
from .capabilities import Capabilities
from .compliance import Compliance
from .cost import CostHint
from .endpoint import Endpoint
from .parameter import Parameter, ParameterSchema
from .trigger import Trigger
from .ui import UIConfig


class OutputSchema(UAPModel):
    """JSON-Schema description of the tool's response payload."""

    schema_: ParameterSchema = Field(..., alias="schema")


class Tool(UAPModel):
    """A single executable capability with full enterprise metadata."""

    id: str = Field(
        ...,
        description="URN: urn:uap:tool:<slug>",
    )
    name: str = Field(..., description="Machine identifier used in invocations.")
    display_name: Optional[str] = None
    description: str
    version: str = Field("0.1.0", description="Semver of the tool definition.")

    parameters: List[Parameter] = Field(default_factory=list)
    output: Optional[OutputSchema] = None

    endpoint: Optional[Endpoint] = None
    triggers: List[Trigger] = Field(default_factory=list)

    auth: Optional[AuthConfig] = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
    compliance: Compliance = Field(default_factory=Compliance)
    cost: Optional[CostHint] = None
    ui: Optional[UIConfig] = None

    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        return validate_urn(v, "tool")

    @field_validator("name")
    @classmethod
    def _name_format(cls, v: str) -> str:
        if not v or not (v[0].isalpha() or v[0] == "_"):
            raise ValueError("Tool.name must start with a letter or underscore.")
        return v
