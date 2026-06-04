# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP -> A2A AgentCard export.

A2A's ``AgentCard`` is a flat agent-level document. It cannot carry
standalone Tool definitions, nor the bulk of UAP's enterprise envelope
(compliance, cost, fine-grained capabilities). Anything that does not
fit the AgentCard shape is either smuggled through ``metadata`` (when
needed for round-tripping) or recorded in the returned :class:`LossInfo`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    AuthType,
    LossInfo,
    Tool,
    Trigger,
    TriggerType,
)


# ---------------------------------------------------------------------------
# Auth mapping
# ---------------------------------------------------------------------------

# A2A's accepted auth schemes. Anything outside this set is recorded as a
# loss and approximated by "bearer".
_DIRECT_AUTH_MAP: Dict[AuthType, str] = {
    AuthType.NONE: "none",
    AuthType.API_KEY: "apiKey",
    AuthType.BEARER: "bearer",
    AuthType.OAUTH2: "oauth2",
}

# UAP auth types that A2A cannot express. They are mapped to "bearer" with
# a LossInfo note.
_APPROXIMATED_AUTH = {AuthType.MTLS, AuthType.AWS_SIGV4, AuthType.GCP_SA}


def _map_auth(auth: AuthConfig | None, loss: LossInfo) -> Dict[str, Any]:
    """Translate UAP ``AuthConfig`` to an A2A ``authentication`` block."""
    if auth is None:
        return {"schemes": ["none"]}

    if auth.type in _DIRECT_AUTH_MAP:
        scheme = _DIRECT_AUTH_MAP[auth.type]
    elif auth.type in _APPROXIMATED_AUTH:
        scheme = "bearer"
        loss.coerced_fields.append("auth.type")
        loss.notes.append(
            f"A2A AgentCard cannot express auth.type={auth.type.value!r}; "
            "approximated as 'bearer'."
        )
    else:  # pragma: no cover — exhaustive over the enum
        scheme = "bearer"
        loss.coerced_fields.append("auth.type")
        loss.notes.append(
            f"Unknown auth.type={auth.type!r}; approximated as 'bearer'."
        )

    block: Dict[str, Any] = {"schemes": [scheme]}

    # AgentCard's `credentials` slot is a free-form opaque string. Pass the
    # secret reference through verbatim so a consumer can resolve it.
    if auth.secret_ref is not None:
        block["credentials"] = auth.secret_ref

    # Other AuthConfig fields are not modelled by A2A.
    for field, path in (
        (auth.scopes, "auth.scopes"),
        (auth.token_url, "auth.token_url"),
        (auth.authorize_url, "auth.authorize_url"),
        (auth.audience, "auth.audience"),
        (auth.header_name, "auth.header_name"),
    ):
        if field:
            loss.dropped_fields.append(path)

    return block


# ---------------------------------------------------------------------------
# Capability mapping
# ---------------------------------------------------------------------------

def _push_notifications_for(agent: Agent) -> bool:
    """A2A 'pushNotifications' = does any tool have a webhook trigger?"""
    for tool in agent.tools:
        if isinstance(tool, Tool):
            for trig in tool.triggers:
                if isinstance(trig, Trigger) and trig.type == TriggerType.WEBHOOK:
                    return True
    return False


def _map_capabilities(agent: Agent, loss: LossInfo) -> Dict[str, bool]:
    caps = agent.capabilities
    a2a_caps = {
        "streaming": caps.supports_streaming,
        "pushNotifications": _push_notifications_for(agent),
        "stateTransitionHistory": caps.long_running,
    }

    # UAP capability fields not present in A2A.
    for path in (
        "capabilities.idempotent",
        "capabilities.side_effects",
        "capabilities.deterministic",
        "capabilities.requires_human_approval",
        "capabilities.supports_cancellation",
        "capabilities.max_concurrency",
    ):
        loss.dropped_fields.append(path)

    return a2a_caps


# ---------------------------------------------------------------------------
# Skill mapping
# ---------------------------------------------------------------------------

def _map_skills(agent: Agent) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for skill in agent.skills:
        out.append(
            {
                "id": skill.id,
                "name": skill.name,
                "description": skill.description,
                "tags": list(skill.tags),
                "examples": list(skill.examples),
                "inputModes": list(skill.input_modes),
                "outputModes": list(skill.output_modes),
            }
        )
    return out


def _default_modes(agent: Agent) -> Tuple[List[str], List[str]]:
    """Derive defaultInputModes / defaultOutputModes from the skill set.

    Falls back to ``["text"]`` when no skills are declared.
    """
    if not agent.skills:
        return (["text"], ["text"])

    inputs: List[str] = []
    outputs: List[str] = []
    seen_in: set[str] = set()
    seen_out: set[str] = set()
    for skill in agent.skills:
        for mode in skill.input_modes:
            if mode not in seen_in:
                seen_in.add(mode)
                inputs.append(mode)
        for mode in skill.output_modes:
            if mode not in seen_out:
                seen_out.add(mode)
                outputs.append(mode)
    return (inputs or ["text"], outputs or ["text"])


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def agent_to_a2a(uap_agent: Agent) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP :class:`Agent` into an A2A ``AgentCard`` dict."""
    loss = LossInfo()

    # Endpoint URL — A2A AgentCard has a single canonical URL. Use the first.
    url = ""
    if uap_agent.endpoints:
        first = uap_agent.endpoints[0]
        url = first.url or ""
        if len(uap_agent.endpoints) > 1:
            loss.dropped_fields.append("endpoints[1:]")
            loss.notes.append(
                "A2A AgentCard has a single 'url' field; only endpoints[0] was kept."
            )
        # Endpoint extras (method, transport != http, timeout) are dropped.
        for path in (
            "endpoints[0].transport",
            "endpoints[0].method",
            "endpoints[0].supports_async",
            "endpoints[0].streaming",
            "endpoints[0].timeout_seconds",
        ):
            loss.dropped_fields.append(path)

    auth_block = _map_auth(uap_agent.auth, loss)
    capabilities = _map_capabilities(uap_agent, loss)
    skills = _map_skills(uap_agent)
    default_in, default_out = _default_modes(uap_agent)

    # Provider block — only emit when at least one field is populated.
    provider: Dict[str, str] = {}
    if uap_agent.publisher:
        provider["organization"] = uap_agent.publisher
    if uap_agent.homepage:
        provider["url"] = uap_agent.homepage

    card: Dict[str, Any] = {
        "name": uap_agent.display_name or uap_agent.name,
        "description": uap_agent.description,
        "url": url,
        "version": uap_agent.version,
        "capabilities": capabilities,
        "authentication": auth_block,
        "defaultInputModes": default_in,
        "defaultOutputModes": default_out,
        "skills": skills,
    }
    if uap_agent.documentation_url is not None:
        card["documentationUrl"] = uap_agent.documentation_url
    if provider:
        card["provider"] = provider

    # ------------------------------------------------------------------
    # Smuggle round-trip metadata so from_a2a can reconstruct the URN,
    # the machine-identifier ``name`` (A2A's ``name`` is display-ish), and
    # the original tool URN list. All other UAP-only fields are dropped
    # (A2A does not preserve unknown keys reliably across implementations,
    # so we deliberately mark them as lost rather than stashing them in
    # metadata).
    # ------------------------------------------------------------------
    metadata: Dict[str, Any] = {
        "uap_urn": uap_agent.id,
        "uap_name": uap_agent.name,
    }

    tool_urns: List[str] = []
    has_inline_tools = False
    for t in uap_agent.tools:
        if isinstance(t, Tool):
            tool_urns.append(t.id)
            has_inline_tools = True
        else:
            # Already a URN string.
            tool_urns.append(t)
    if tool_urns:
        metadata["uap_tools"] = tool_urns
        loss.dropped_fields.append("tools")
        loss.notes.append(
            "A2A AgentCard does not model Tools as first-class objects; "
            "tool URNs stored in metadata.uap_tools."
        )
        if has_inline_tools:
            loss.notes.append(
                "Inline Tool definitions were reduced to URN references; "
                "Tool bodies must be re-fetched via the registry."
            )

    card["metadata"] = metadata

    # ------------------------------------------------------------------
    # Record dropped UAP-only fields explicitly. These are spec-required
    # entries: silent omission is forbidden.
    # ------------------------------------------------------------------
    for path in (
        "compliance.data_classification",
        "compliance.pii",
        "compliance.regulations",
        "compliance.data_residency",
        "compliance.retention_days",
        "compliance.audit_log",
        "ui",
        "tags",
    ):
        loss.dropped_fields.append(path)

    if uap_agent.metadata:
        # User-supplied metadata is not propagated; we only emit our own
        # round-trip helpers in metadata.
        loss.dropped_fields.append("metadata")
        loss.notes.append(
            "User-supplied Agent.metadata was not forwarded; A2A metadata is "
            "reserved here for UAP round-trip helpers."
        )

    return card, loss


def to_a2a(obj: Any) -> Tuple[Dict[str, Any], LossInfo]:
    """Public dispatcher. Rejects :class:`Tool` (A2A is agent-level only)."""
    if isinstance(obj, Tool):
        raise ValueError(
            "A2A AgentCard does not model standalone Tools. "
            "Wrap the tool in an Agent before exporting."
        )
    if isinstance(obj, Agent):
        return agent_to_a2a(obj)
    raise TypeError(
        f"to_a2a expected an Agent, got {type(obj).__name__}"
    )
