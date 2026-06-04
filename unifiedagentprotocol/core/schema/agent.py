# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Agent and Skill — the orchestration-facing entity."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import Field, field_validator

from ._base import UAPModel, validate_urn
from .auth import AuthConfig
from .capabilities import Capabilities
from .compliance import Compliance
from .endpoint import Endpoint
from .tool import Tool
from .ui import UIConfig


class Skill(UAPModel):
    """A named capability of an Agent, possibly composed from several tools.

    A skill is the unit that A2A surfaces to other agents. Compare with
    A2A AgentCard.skills.
    """

    id: str
    name: str
    description: str
    input_modes: List[str] = Field(
        default_factory=lambda: ["text"],
        description='Modalities accepted, e.g. ["text", "image", "audio"].',
    )
    output_modes: List[str] = Field(default_factory=lambda: ["text"])
    examples: List[str] = Field(
        default_factory=list,
        description="Natural-language example invocations.",
    )
    tags: List[str] = Field(default_factory=list)


class Agent(UAPModel):
    """An autonomous actor exposing one or more skills and tools."""

    id: str = Field(..., description="URN: urn:uap:agent:<slug>")
    name: str
    display_name: Optional[str] = None
    description: str
    version: str = Field("0.1.0", description="Semver of the agent definition.")

    tools: List[Union[Tool, str]] = Field(
        default_factory=list,
        description="Inline Tool definitions OR Tool URNs to resolve later.",
    )
    skills: List[Skill] = Field(default_factory=list)
    endpoints: List[Endpoint] = Field(default_factory=list)

    auth: Optional[AuthConfig] = None
    capabilities: Capabilities = Field(default_factory=Capabilities)
    compliance: Compliance = Field(default_factory=Compliance)
    ui: Optional[UIConfig] = None

    documentation_url: Optional[str] = None
    homepage: Optional[str] = None
    publisher: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        return validate_urn(v, "agent")
