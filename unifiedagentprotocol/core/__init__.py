# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP 1.0 — Core Intermediate Representation.

This package is the wire-format source-of-truth as Python models. Pydantic v2
native. No network calls, no I/O. Importable from any environment.

The canonical JSON Schemas live in ``schemas/uap/1.0/`` and are kept in sync
with these models via ``tests/core/test_schema_sync.py``.
"""
from __future__ import annotations

from .version import UAP_VERSION, SDK_VERSION
from .lossinfo import LossInfo
from .schema.parameter import Parameter, ParameterLocation, ParameterSchema
from .schema.tool import Tool
from .schema.agent import Agent, Skill
from .schema.auth import AuthConfig, AuthType
from .schema.capabilities import Capabilities, SideEffects
from .schema.compliance import Compliance, DataClassification, PIILevel
from .schema.cost import CostHint
from .schema.endpoint import Endpoint, Transport
from .schema.trigger import Trigger, TriggerType
from .schema.ui import UIConfig
from .schema.manifest import Manifest
from .schema.envelope import Envelope, Kind

__all__ = [
    "UAP_VERSION",
    "SDK_VERSION",
    "LossInfo",
    "Parameter",
    "ParameterLocation",
    "ParameterSchema",
    "Tool",
    "Agent",
    "Skill",
    "AuthConfig",
    "AuthType",
    "Capabilities",
    "SideEffects",
    "Compliance",
    "DataClassification",
    "PIILevel",
    "CostHint",
    "Endpoint",
    "Transport",
    "Trigger",
    "TriggerType",
    "UIConfig",
    "Manifest",
    "Envelope",
    "Kind",
]
