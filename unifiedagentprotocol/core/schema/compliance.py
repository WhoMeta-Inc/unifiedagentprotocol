# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Compliance metadata — data classification, residency, retention."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import Field

from ._base import UAPModel


class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class PIILevel(str, Enum):
    NONE = "none"
    LOW = "low"
    HIGH = "high"


class Compliance(UAPModel):
    """Procurement-time compliance properties.

    These fields are intentionally coarse: they are *labels* the policy
    engine consumes, not formal proofs. Auditors use them to scope tools
    in or out of a process.
    """

    data_classification: DataClassification = DataClassification.INTERNAL
    pii: PIILevel = PIILevel.NONE
    regulations: List[str] = Field(
        default_factory=list,
        description='ISO short codes, e.g. ["GDPR", "HIPAA", "SOC2", "PCI-DSS"]',
    )
    data_residency: List[str] = Field(
        default_factory=list,
        description='Region codes such as "EU", "US", "DE", "CH".',
    )
    retention_days: Optional[int] = Field(
        None,
        ge=0,
        description=(
            "Maximum retention of caller payloads, in days. "
            "None = unspecified, 0 = no retention."
        ),
    )
    audit_log: bool = True
