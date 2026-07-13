# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Tenant-scoped, side-effect-free matching for a UAP agent directory.

This module deliberately does not expose a network or persistence boundary.
Applications can project their authoritative workforce data into ``Agent``
metadata and use this matcher before creating a governed delegation task.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from unifiedagentprotocol.core import Agent, Kind
from unifiedagentprotocol.registry_impl.base import Registry

AVAILABLE_STATES = {"active", "available", "working"}


def _normalized(values: Iterable[str]) -> set[str]:
    return {value.strip().casefold() for value in values if value.strip()}


def _number(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _metadata(agent: Agent) -> Mapping[str, Any]:
    return agent.metadata if isinstance(agent.metadata, dict) else {}


def _capability_tags(agent: Agent) -> set[str]:
    tags = _normalized(agent.tags)
    for skill in agent.skills:
        tags.update(_normalized(skill.tags))
        tags.add(skill.id.strip().casefold())
        tags.add(skill.name.strip().casefold())
    return tags


@dataclass(frozen=True)
class DirectoryMatch:
    """A ranked candidate and the explainable inputs used for its score."""

    agent: Agent
    matched_capabilities: tuple[str, ...]
    evaluation_score: float
    available_capacity: float
    external: bool

    @property
    def score(self) -> tuple[int, float, float, str]:
        return (
            len(self.matched_capabilities),
            self.evaluation_score,
            self.available_capacity,
            self.agent.id,
        )


def match_agents(
    registry: Registry,
    *,
    tenant_id: str,
    required_capabilities: Sequence[str],
    delegation_chain: Sequence[str] = (),
    include_external: bool = False,
    limit: int = 20,
) -> list[DirectoryMatch]:
    """Return available same-tenant agents ranked for a delegation.

    Metadata conventions are intentionally additive and portable:

    - ``tenant_id`` is mandatory and must exactly match the caller tenant;
    - ``availability`` defaults to unavailable and must be active/available/working;
    - ``available_capacity`` is a number greater than zero;
    - ``evaluation_score`` is a normalized quality hint used only for ranking;
    - ``external`` agents require both ``include_external`` and
      ``external_approved``.

    Every requested capability must match a skill id, skill name, skill tag, or
    agent tag. Agents already present in ``delegation_chain`` are excluded,
    which gives callers a deterministic primitive for cycle prevention.
    """
    if not tenant_id.strip() or limit <= 0:
        return []
    required = _normalized(required_capabilities)
    if not required:
        return []
    chain = set(delegation_chain)
    matches: list[DirectoryMatch] = []

    for record in registry.list(kind=Kind.AGENT):
        if not isinstance(record, Agent) or record.id in chain:
            continue
        metadata = _metadata(record)
        if metadata.get("tenant_id") != tenant_id:
            continue
        availability = str(metadata.get("availability") or "").casefold()
        if availability not in AVAILABLE_STATES:
            continue
        capacity = _number(metadata.get("available_capacity"))
        if capacity <= 0:
            continue
        external = metadata.get("external") is True
        if external and (not include_external or metadata.get("external_approved") is not True):
            continue

        available_tags = _capability_tags(record)
        matched = required.intersection(available_tags)
        if matched != required:
            continue
        evaluation = max(0.0, min(1.0, _number(metadata.get("evaluation_score"))))
        matches.append(
            DirectoryMatch(
                agent=record,
                matched_capabilities=tuple(sorted(matched)),
                evaluation_score=evaluation,
                available_capacity=capacity,
                external=external,
            )
        )

    matches.sort(key=lambda item: item.score, reverse=True)
    return matches[:limit]


__all__ = ["DirectoryMatch", "match_agents"]
