# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Governed UAP task-envelope contract for persistent A2A runtimes.

The core :class:`Envelope` publishes definitions.  ``TaskEnvelope`` is the
runtime message that submits a bounded unit of work and carries the security
material a persistent task bus needs for tenant binding and replay protection.
Key material and signature verification deliberately remain runtime-owned.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _urn(value: str, kind: str) -> str:
    prefix = f"urn:uap:{kind}:"
    slug = value.removeprefix(prefix)
    if not value.startswith(prefix) or not slug or any(
        not (char.isascii() and (char.isalnum() or char in "._-")) for char in slug
    ):
        raise ValueError(f"Expected {prefix}<slug>")
    return value


class AgentTaskPayload(BaseModel):
    """Data-minimized work package; tenant is always carried by the envelope."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_agent: str
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=20_000)
    correlation_id: str | None = Field(default=None, max_length=128)

    @field_validator("target_agent")
    @classmethod
    def _target_is_agent_urn(cls, value: str) -> str:
        return _urn(value, "agent")


class TaskEnvelope(BaseModel):
    """UAP 1.0 A2A task message signed over :meth:`canonical_statement`.

    ``connection_id`` selects an already approved counterparty.  It is not an
    authorization assertion: the receiver binds it to the stored producer URN,
    external tenant, public key and endpoint allowlist before accepting work.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    uap_version: Literal["1.0"] = "1.0"
    kind: Literal["agent.task"] = "agent.task"
    id: str = Field(max_length=128)
    connection_id: UUID
    produced_by: str = Field(max_length=512)
    tenant_id: str = Field(min_length=1, max_length=128)
    nonce: str = Field(min_length=1, max_length=128)
    expires_at: datetime
    payload: AgentTaskPayload
    signature: str = Field(pattern=r"^ed25519:[A-Za-z0-9+/]+={0,2}$")

    @field_validator("id")
    @classmethod
    def _id_is_task_urn(cls, value: str) -> str:
        return _urn(value, "task")

    @field_validator("produced_by")
    @classmethod
    def _producer_is_agent_urn(cls, value: str) -> str:
        return _urn(value, "agent")

    @field_validator("expires_at")
    @classmethod
    def _expiry_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("expires_at must include a timezone")
        return value.astimezone(timezone.utc)

    def canonical_statement(self) -> str:
        """Return the cross-language statement covered by the Ed25519 signature."""

        def field(value: str | None) -> str:
            return base64.b64encode((value or "").encode("utf-8")).decode("ascii")

        return "\n".join(
            (
                field(self.uap_version),
                field(self.kind),
                field(self.id),
                field(str(self.connection_id)),
                field(self.produced_by),
                field(self.tenant_id),
                field(self.nonce),
                str(int(self.expires_at.timestamp())),
                field(self.payload.target_agent),
                field(self.payload.title),
                field(self.payload.description),
                field(self.payload.correlation_id),
            )
        )
