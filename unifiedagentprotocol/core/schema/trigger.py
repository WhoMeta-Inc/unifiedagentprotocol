# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Trigger — when/how a Tool or Agent activates."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import Field, model_validator

from ._base import UAPModel


class TriggerType(str, Enum):
    MANUAL = "manual"
    CRON = "cron"
    WEBHOOK = "webhook"
    INTENT = "intent"
    EVENT = "event"


class Trigger(UAPModel):
    """Activation contract for a Tool or Agent."""

    type: TriggerType = TriggerType.MANUAL
    cron: Optional[str] = Field(None, description="Five-field cron, UTC.")
    intent_pattern: Optional[str] = Field(
        None,
        description="Regex or glob matched against natural-language input.",
    )
    webhook_path: Optional[str] = Field(
        None,
        description='Path mounted by the runtime (e.g. "/hooks/weather").',
    )
    event_name: Optional[str] = None
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _consistency(self) -> "Trigger":
        required_by_type = {
            TriggerType.CRON: ("cron", self.cron),
            TriggerType.INTENT: ("intent_pattern", self.intent_pattern),
            TriggerType.WEBHOOK: ("webhook_path", self.webhook_path),
            TriggerType.EVENT: ("event_name", self.event_name),
        }
        if self.type in required_by_type:
            field_name, value = required_by_type[self.type]
            if not value:
                raise ValueError(
                    f"Trigger.type={self.type.value} requires field '{field_name}'."
                )
        return self
