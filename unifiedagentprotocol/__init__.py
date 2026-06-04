# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Unified Agent Protocol — Core SDK.

UAP 1.0 — the universal interoperability layer for AI agents and tools.

Top-level re-exports:

    from unifiedagentprotocol import (
        Tool, Agent, Skill, Manifest, Envelope,
        Parameter, ParameterSchema,
        AuthConfig, Capabilities, Compliance, CostHint,
        Endpoint, Trigger, UIConfig,
        LossInfo, UAP_VERSION, SDK_VERSION,
    )

Bridges live under ``unifiedagentprotocol.bridges.<format>`` and follow the
``to_<format>`` / ``from_<format>`` contract.
"""
from __future__ import annotations

from .core import (
    UAP_VERSION,
    SDK_VERSION,
    LossInfo,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    Tool,
    Agent,
    Skill,
    AuthConfig,
    AuthType,
    Capabilities,
    SideEffects,
    Compliance,
    DataClassification,
    PIILevel,
    CostHint,
    Endpoint,
    Transport,
    Trigger,
    TriggerType,
    UIConfig,
    Manifest,
    Envelope,
    Kind,
)

__version__ = SDK_VERSION

__all__ = [
    "UAP_VERSION",
    "SDK_VERSION",
    "__version__",
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
