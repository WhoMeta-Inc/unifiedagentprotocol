# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Authentication configuration. Secrets are referenced, never inlined."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import Field, field_validator

from ._base import UAPModel


class AuthType(str, Enum):
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH2 = "oauth2"
    MTLS = "mtls"
    AWS_SIGV4 = "aws_sigv4"
    GCP_SA = "gcp_service_account"


class AuthConfig(UAPModel):
    """Authentication contract for invoking a Tool or Agent.

    The ``secret_ref`` field MUST be a URI to an external secret store
    (vault://, aws-sm://, gcp-sm://, env://NAME). Inline secrets are
    rejected to keep UAP payloads safe to ship.
    """

    type: AuthType = AuthType.NONE
    scopes: List[str] = Field(default_factory=list)
    token_url: Optional[str] = None
    authorize_url: Optional[str] = None
    audience: Optional[str] = None
    header_name: Optional[str] = Field(
        None,
        description='Header name for "api_key" or "bearer" (default: Authorization).',
    )
    secret_ref: Optional[str] = Field(
        None,
        description=(
            "Reference to the secret material. Schemes: "
            "vault://, aws-sm://, gcp-sm://, env://NAME"
        ),
    )

    @field_validator("secret_ref")
    @classmethod
    def _no_inline_secrets(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        allowed = ("vault://", "aws-sm://", "gcp-sm://", "env://", "file://")
        if not any(v.startswith(p) for p in allowed):
            raise ValueError(
                "secret_ref must reference an external secret store "
                f"(one of {allowed}). Inline secrets are forbidden."
            )
        return v
