# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Endpoint — how an external caller reaches a Tool or Agent."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator

from ._base import UAPModel


class Transport(str, Enum):
    HTTP = "http"
    SSE = "sse"
    WEBSOCKET = "websocket"
    STDIO = "stdio"
    GRPC = "grpc"
    NATS = "nats"


_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


class Endpoint(UAPModel):
    """A network-addressable interface for invoking a Tool or Agent."""

    transport: Transport = Transport.HTTP
    url: Optional[str] = Field(
        None,
        description='Full URL or stdio command. Empty for in-process tools.',
    )
    method: Optional[str] = Field(
        None,
        description="HTTP method. Required when transport=http.",
    )
    streaming: bool = False
    supports_async: bool = Field(
        False,
        description="Whether the endpoint supports task-id polling / callbacks.",
    )
    timeout_seconds: Optional[int] = Field(None, ge=0)

    @field_validator("method")
    @classmethod
    def _http_method(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if v.upper() not in _HTTP_METHODS:
            raise ValueError(
                f"Endpoint.method must be one of {sorted(_HTTP_METHODS)}; got {v!r}"
            )
        return v.upper()
