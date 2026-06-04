# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Manifest — a publishable bundle of Agents and Tools."""
from __future__ import annotations

from typing import List, Optional, Union

from pydantic import Field, field_validator

from ._base import UAPModel, validate_urn
from .agent import Agent
from .tool import Tool


class Manifest(UAPModel):
    """A registry-publishable bundle.

    Bundles MAY embed full Agent/Tool definitions or reference them by URN.
    Registries are expected to resolve URN references at fetch time.
    """

    id: str = Field(..., description="URN: urn:uap:manifest:<slug>")
    name: str
    description: str
    version: str = "0.1.0"

    agents: List[Union[Agent, str]] = Field(default_factory=list)
    tools: List[Union[Tool, str]] = Field(default_factory=list)

    publisher: Optional[str] = None
    homepage: Optional[str] = None
    license: Optional[str] = None
    tags: List[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        return validate_urn(v, "manifest")
