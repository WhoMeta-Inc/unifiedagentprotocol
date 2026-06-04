# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Envelope — the outermost wire-format wrapper.

Every UAP payload travelling over the wire is wrapped in an Envelope so
that consumers can dispatch on ``kind`` and reject incompatible
``uap_version``.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import Field, field_validator

from ..version import UAP_VERSION, SDK_VERSION, is_compatible
from ._base import UAPModel
from .agent import Agent
from .manifest import Manifest
from .tool import Tool


class Kind(str, Enum):
    AGENT = "agent"
    TOOL = "tool"
    MANIFEST = "manifest"


_KIND_TO_TYPE = {
    Kind.AGENT: Agent,
    Kind.TOOL: Tool,
    Kind.MANIFEST: Manifest,
}


class Envelope(UAPModel):
    """The outermost wire object. Carries version and dispatch metadata."""

    uap_version: str = UAP_VERSION
    kind: Kind
    id: str
    payload: Union[Agent, Tool, Manifest]
    signature: Optional[str] = Field(
        None,
        description="Optional Ed25519 signature over the canonical payload JSON.",
    )
    produced_by: str = Field(
        default=f"uap-core/{SDK_VERSION}",
        description="User-Agent-like identifier of the producer.",
    )

    @field_validator("uap_version")
    @classmethod
    def _check_compat(cls, v: str) -> str:
        if not is_compatible(v):
            raise ValueError(
                f"Incompatible uap_version {v!r}; this SDK is {UAP_VERSION}"
            )
        return v

    @classmethod
    def of(cls, obj: Union[Agent, Tool, Manifest]) -> "Envelope":
        for kind, typ in _KIND_TO_TYPE.items():
            if isinstance(obj, typ):
                return cls(kind=kind, id=obj.id, payload=obj)
        raise TypeError(f"Cannot wrap object of type {type(obj).__name__}")
