# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Example 1 — Define a UAP Tool and Agent with full enterprise metadata."""
from __future__ import annotations

import json

from unifiedagentprotocol import (
    Agent,
    AuthConfig,
    AuthType,
    Capabilities,
    Compliance,
    CostHint,
    DataClassification,
    Endpoint,
    Envelope,
    PIILevel,
    Parameter,
    ParameterSchema,
    SideEffects,
    Skill,
    Tool,
    Transport,
    Trigger,
    TriggerType,
    UIConfig,
)


tool = Tool(
    id="urn:uap:tool:get-weather",
    name="get_weather",
    display_name="Get Weather",
    description="Return the current weather for a city.",
    version="1.0.0",
    parameters=[
        Parameter(
            name="city",
            schema=ParameterSchema(
                type="string",
                description="Target city name.",
                min_length=1,
                max_length=100,
            ),
            required=True,
        )
    ],
    output={"schema": {"type": "object", "properties": {"temp_c": {"type": "number"}}}},
    endpoint=Endpoint(
        transport=Transport.HTTP,
        url="https://api.example.com/weather",
        method="POST",
    ),
    triggers=[Trigger(type=TriggerType.INTENT, intent_pattern="^/weather")],
    auth=AuthConfig(type=AuthType.API_KEY, secret_ref="vault://kv/data/weather#token"),
    capabilities=Capabilities(
        idempotent=True,
        side_effects=SideEffects.READ_ONLY,
        deterministic=False,
        requires_human_approval=False,
        supports_streaming=False,
    ),
    compliance=Compliance(
        data_classification=DataClassification.PUBLIC,
        pii=PIILevel.NONE,
        regulations=["GDPR"],
        data_residency=["EU"],
        retention_days=0,
    ),
    cost=CostHint(per_call_usd=0.0001, latency_ms_p50=120, latency_ms_p99=900),
    ui=UIConfig(label="Weather", icon="mdi:weather-partly-cloudy", color="#00aaff"),
    tags=["weather", "public"],
)

agent = Agent(
    id="urn:uap:agent:weather-bot",
    name="WeatherBot",
    display_name="Weather Bot",
    description="Provides weather information and forecasts.",
    version="1.0.0",
    tools=[tool],
    skills=[
        Skill(
            id="answer-weather",
            name="answer-weather",
            description="Reply with current weather for a city.",
            examples=["What's the weather in Berlin?"],
        )
    ],
    endpoints=[Endpoint(transport=Transport.HTTP, url="https://bot.example.com")],
    publisher="WhoMeta",
    homepage="https://www.whometa.io",
)


if __name__ == "__main__":
    envelope = Envelope.of(agent)
    print(json.dumps(envelope.to_wire(), indent=2))
