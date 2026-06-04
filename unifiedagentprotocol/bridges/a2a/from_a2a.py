# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""A2A AgentCard -> UAP import.

Reconstructs a UAP :class:`Agent` from an A2A ``AgentCard`` dict. Fields
the AgentCard cannot supply (compliance, cost, fine-grained capabilities)
are populated with safe UAP defaults and recorded as approximated /
missing in the returned :class:`LossInfo`.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    AuthType,
    Capabilities,
    Endpoint,
    LossInfo,
    Skill,
    Transport,
)


# ---------------------------------------------------------------------------
# URN helpers
# ---------------------------------------------------------------------------

_SLUG_INVALID = re.compile(r"[^a-z0-9._-]+")
_SLUG_LEAD = re.compile(r"^[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Lowercase, replace non-[a-z0-9._-] with '-', strip illegal lead chars."""
    lowered = name.strip().lower()
    slug = _SLUG_INVALID.sub("-", lowered)
    slug = _SLUG_LEAD.sub("", slug)
    slug = slug.strip("-._")
    return slug or "unnamed"


# ---------------------------------------------------------------------------
# Auth mapping
# ---------------------------------------------------------------------------

_A2A_AUTH_TO_UAP: Dict[str, AuthType] = {
    "none": AuthType.NONE,
    "apiKey": AuthType.API_KEY,
    "bearer": AuthType.BEARER,
    "oauth2": AuthType.OAUTH2,
}


def _map_auth(auth_block: Dict[str, Any] | None, loss: LossInfo) -> AuthConfig | None:
    if not auth_block:
        return None
    schemes = auth_block.get("schemes") or []
    if not schemes:
        return None

    first = schemes[0]
    if len(schemes) > 1:
        loss.dropped_fields.append("authentication.schemes[1:]")
        loss.notes.append(
            "UAP AuthConfig models a single auth type; "
            f"only the first scheme {first!r} was kept."
        )

    auth_type = _A2A_AUTH_TO_UAP.get(first)
    if auth_type is None:
        loss.coerced_fields.append("authentication.schemes[0]")
        loss.notes.append(
            f"Unknown A2A auth scheme {first!r}; approximated as 'bearer'."
        )
        auth_type = AuthType.BEARER

    creds = auth_block.get("credentials")
    secret_ref: str | None = None
    if creds:
        # AuthConfig.secret_ref requires an external-store URI. Plain inline
        # values cannot be accepted; record loss and drop.
        allowed = ("vault://", "aws-sm://", "gcp-sm://", "env://", "file://")
        if isinstance(creds, str) and any(creds.startswith(p) for p in allowed):
            secret_ref = creds
        else:
            loss.dropped_fields.append("authentication.credentials")
            loss.notes.append(
                "A2A authentication.credentials was not an external secret URI; "
                "UAP forbids inline secrets so the value was discarded."
            )

    cfg = AuthConfig(type=auth_type, secret_ref=secret_ref)

    if auth_type == AuthType.BEARER and secret_ref is None:
        loss.notes.append(
            "Bearer auth imported without a secret_ref; the AgentCard did not "
            "supply credentials. Set AuthConfig.secret_ref before invoking the agent."
        )

    return cfg


# ---------------------------------------------------------------------------
# Capability mapping
# ---------------------------------------------------------------------------

def _map_capabilities(card: Dict[str, Any], loss: LossInfo) -> Capabilities:
    raw = card.get("capabilities") or {}
    # AgentCard cannot supply the rest of the UAP capabilities; we
    # populate them with the schema defaults and record the missing input.
    caps = Capabilities(
        supports_streaming=bool(raw.get("streaming", False)),
        long_running=bool(raw.get("stateTransitionHistory", False)),
    )
    for path in (
        "capabilities.idempotent",
        "capabilities.side_effects",
        "capabilities.deterministic",
        "capabilities.requires_human_approval",
        "capabilities.supports_cancellation",
        "capabilities.max_concurrency",
    ):
        loss.notes.append(
            f"{path} not present in A2A AgentCard; defaulted by UAP schema."
        )
    if raw.get("pushNotifications"):
        # pushNotifications is captured by virtue of webhook triggers on
        # the tools. We do not invent tools here; record the signal so a
        # consumer can attach an explicit webhook Trigger later.
        loss.notes.append(
            "A2A capabilities.pushNotifications=True but UAP encodes this via "
            "Tool.triggers[type=webhook]; no synthetic webhook trigger was added."
        )
    return caps


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def _map_skills(card: Dict[str, Any]) -> List[Skill]:
    out: List[Skill] = []
    for entry in card.get("skills") or []:
        if not isinstance(entry, dict):
            continue
        out.append(
            Skill(
                id=str(entry.get("id") or _slugify(str(entry.get("name", "skill")))),
                name=str(entry.get("name") or entry.get("id") or "skill"),
                description=str(entry.get("description") or ""),
                input_modes=list(entry.get("inputModes") or ["text"]),
                output_modes=list(entry.get("outputModes") or ["text"]),
                examples=list(entry.get("examples") or []),
                tags=list(entry.get("tags") or []),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def agent_from_a2a(agent_card: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Reconstruct a UAP :class:`Agent` from an A2A AgentCard dict."""
    if not isinstance(agent_card, dict):
        raise TypeError(
            f"agent_from_a2a expected a dict, got {type(agent_card).__name__}"
        )

    loss = LossInfo()

    display_name_raw = str(agent_card.get("name") or "agent")
    description = str(agent_card.get("description") or "")
    version = str(agent_card.get("version") or "0.1.0")
    url = agent_card.get("url") or None

    metadata_in: Dict[str, Any] = dict(agent_card.get("metadata") or {})

    # Recover the original URN if to_a2a smuggled it through metadata.
    urn = metadata_in.pop("uap_urn", None)
    if isinstance(urn, str) and urn.startswith("urn:uap:agent:"):
        agent_id = urn
    else:
        agent_id = f"urn:uap:agent:{_slugify(display_name_raw)}"
        loss.notes.append(
            "AgentCard did not carry metadata.uap_urn; URN synthesized "
            f"from name as {agent_id!r}."
        )

    # Recover the machine-identifier name if smuggled; otherwise reuse the
    # display name (which may not be a strict identifier).
    machine_name_meta = metadata_in.pop("uap_name", None)
    name_raw = (
        machine_name_meta
        if isinstance(machine_name_meta, str) and machine_name_meta
        else display_name_raw
    )

    # Recover tool URNs (if any). Inline Tool bodies are not in AgentCard,
    # so they remain bare URN strings — the caller must resolve them via
    # a registry if Tool definitions are required.
    tool_urns_meta = metadata_in.pop("uap_tools", None)
    tools: List[Any] = []
    if isinstance(tool_urns_meta, list):
        for t in tool_urns_meta:
            if isinstance(t, str) and t.startswith("urn:uap:tool:"):
                tools.append(t)
            else:
                loss.dropped_fields.append("metadata.uap_tools[invalid]")

    endpoints: List[Endpoint] = []
    if url:
        endpoints.append(Endpoint(transport=Transport.HTTP, url=url))

    auth = _map_auth(agent_card.get("authentication"), loss)
    capabilities = _map_capabilities(agent_card, loss)
    skills = _map_skills(agent_card)

    provider = agent_card.get("provider") or {}
    publisher = provider.get("organization") if isinstance(provider, dict) else None
    homepage = provider.get("url") if isinstance(provider, dict) else None

    # Anything left in metadata after our extractions is preserved verbatim.
    preserved_metadata = metadata_in

    # Track A2A fields that have no UAP equivalent for transparency.
    if agent_card.get("defaultInputModes") and not skills:
        loss.notes.append(
            "AgentCard.defaultInputModes was preserved on agent skills only when "
            "skills are present; standalone defaults are not modelled in UAP."
        )
    if agent_card.get("defaultOutputModes") and not skills:
        loss.notes.append(
            "AgentCard.defaultOutputModes was preserved on agent skills only when "
            "skills are present; standalone defaults are not modelled in UAP."
        )

    agent = Agent(
        id=agent_id,
        name=name_raw,
        display_name=display_name_raw,
        description=description,
        version=version,
        tools=tools,
        skills=skills,
        endpoints=endpoints,
        auth=auth,
        capabilities=capabilities,
        documentation_url=agent_card.get("documentationUrl"),
        homepage=homepage,
        publisher=publisher,
        metadata=preserved_metadata,
    )

    return agent, loss


def from_a2a(obj: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Alias for :func:`agent_from_a2a`."""
    return agent_from_a2a(obj)
