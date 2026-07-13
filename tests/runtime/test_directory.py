# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
from __future__ import annotations

from unifiedagentprotocol.core import Agent, Skill
from unifiedagentprotocol.registry_impl import InMemoryRegistry
from unifiedagentprotocol.runtime import match_agents


def _agent(
    slug: str,
    *,
    tenant_id: str = "tenant-a",
    tags: list[str] | None = None,
    availability: str = "available",
    capacity: float = 50,
    evaluation: float = 0.5,
    external: bool = False,
    approved: bool = False,
) -> Agent:
    return Agent(
        id=f"urn:uap:agent:{slug}",
        name=slug,
        description=f"{slug} test agent",
        skills=[
            Skill(
                id="skill.research",
                name="Research",
                description="Research evidence",
                tags=tags or ["research"],
            )
        ],
        metadata={
            "tenant_id": tenant_id,
            "availability": availability,
            "available_capacity": capacity,
            "evaluation_score": evaluation,
            "external": external,
            "external_approved": approved,
        },
    )


def test_match_is_tenant_scoped_and_ranks_evaluation_then_capacity() -> None:
    registry = InMemoryRegistry()
    registry.register(_agent("lower", evaluation=0.6, capacity=90))
    registry.register(_agent("best", evaluation=0.9, capacity=20))
    registry.register(_agent("other-tenant", tenant_id="tenant-b", evaluation=1.0))

    matches = match_agents(
        registry,
        tenant_id="tenant-a",
        required_capabilities=["RESEARCH"],
    )

    assert [item.agent.name for item in matches] == ["best", "lower"]
    assert matches[0].matched_capabilities == ("research",)


def test_match_requires_every_capability_and_available_capacity() -> None:
    registry = InMemoryRegistry()
    registry.register(_agent("complete", tags=["research", "evidence"]))
    registry.register(_agent("partial", tags=["research"]))
    registry.register(_agent("full", tags=["research", "evidence"], capacity=0))
    registry.register(
        _agent(
            "paused",
            tags=["research", "evidence"],
            availability="paused",
        )
    )

    matches = match_agents(
        registry,
        tenant_id="tenant-a",
        required_capabilities=["research", "evidence"],
    )

    assert [item.agent.name for item in matches] == ["complete"]


def test_delegation_chain_prevents_cycle() -> None:
    registry = InMemoryRegistry()
    agent = _agent("already-visited")
    registry.register(agent)

    matches = match_agents(
        registry,
        tenant_id="tenant-a",
        required_capabilities=["skill.research"],
        delegation_chain=[agent.id],
    )

    assert matches == []


def test_external_agent_requires_query_and_admin_approval() -> None:
    registry = InMemoryRegistry()
    registry.register(_agent("internal"))
    registry.register(_agent("unapproved", external=True))
    registry.register(_agent("approved", external=True, approved=True, evaluation=0.8))

    internal_only = match_agents(
        registry,
        tenant_id="tenant-a",
        required_capabilities=["research"],
    )
    with_external = match_agents(
        registry,
        tenant_id="tenant-a",
        required_capabilities=["research"],
        include_external=True,
    )

    assert [item.agent.name for item in internal_only] == ["internal"]
    assert [item.agent.name for item in with_external] == ["approved", "internal"]


def test_empty_capability_or_invalid_limit_returns_no_candidate() -> None:
    registry = InMemoryRegistry()
    registry.register(_agent("candidate"))

    assert match_agents(registry, tenant_id="tenant-a", required_capabilities=[]) == []
    assert (
        match_agents(
            registry,
            tenant_id="tenant-a",
            required_capabilities=["research"],
            limit=0,
        )
        == []
    )
