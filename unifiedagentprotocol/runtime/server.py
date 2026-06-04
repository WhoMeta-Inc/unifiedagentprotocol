# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""FastAPI adapter for the UAP registry.

The :func:`create_app` factory wraps any :class:`Registry` into a small
read-only HTTP surface:

* ``/healthz``                                 — liveness probe
* ``/.well-known/agent.json``                  — single agent: A2A
  AgentCard. Multiple agents: short index list.
* ``/agents`` / ``/agents/{slug}``             — UAP envelopes
* ``/agents/{slug}/.well-known/agent.json``    — per-agent A2A card
* ``/tools`` / ``/tools/{slug}``               — UAP envelopes
* ``/manifests``                               — UAP envelopes
* ``/mcp/tools``                               — best-effort MCP tools
* ``/openapi-uap.json``                        — aggregated OpenAPI doc

``fastapi`` is imported lazily inside the factory so that simply
importing this module does not require the runtime extra to be
installed. Calling :func:`create_app` without FastAPI installed raises
a helpful :class:`ImportError`.

This module is the *only* file in ``unifiedagentprotocol`` allowed to
import FastAPI; registries and bridges remain framework-agnostic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from unifiedagentprotocol.core import (
    SDK_VERSION,
    UAP_VERSION,
    Agent,
    Capabilities,
    Compliance,
    Envelope,
    Kind,
    Manifest,
    SideEffects,
    Tool,
)

from unifiedagentprotocol.registry_impl.base import Registry, RegistryObject


if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dump(obj: Any) -> Dict[str, Any]:
    """Serialise a pydantic model with the UAP wire conventions."""
    return obj.model_dump(mode="json", exclude_none=True, by_alias=True)


def _envelope(obj: RegistryObject) -> Dict[str, Any]:
    """Wrap a record in its UAP Envelope and dump to JSON-friendly dict."""
    return _dump(Envelope.of(obj))


def _slug_of(urn: str) -> str:
    return urn.rsplit(":", 1)[-1]


def _kind_of(obj: RegistryObject) -> Kind:
    if isinstance(obj, Agent):
        return Kind.AGENT
    if isinstance(obj, Tool):
        return Kind.TOOL
    if isinstance(obj, Manifest):
        return Kind.MANIFEST
    raise TypeError(f"Unsupported registry record type {type(obj).__name__}")


def _agents(registry: Registry) -> List[Agent]:
    return [obj for obj in registry.list(kind=Kind.AGENT) if isinstance(obj, Agent)]


def _tools(registry: Registry) -> List[Tool]:
    return [obj for obj in registry.list(kind=Kind.TOOL) if isinstance(obj, Tool)]


def _manifests(registry: Registry) -> List[Manifest]:
    return [
        obj for obj in registry.list(kind=Kind.MANIFEST) if isinstance(obj, Manifest)
    ]


def _find_agent_by_slug(registry: Registry, slug: str) -> Optional[Agent]:
    for agent in _agents(registry):
        if _slug_of(agent.id) == slug:
            return agent
    return None


def _find_tool_by_slug(registry: Registry, slug: str) -> Optional[Tool]:
    for tool in _tools(registry):
        if _slug_of(tool.id) == slug:
            return tool
    return None


def _aggregator_agent(tools: List[Tool], base_url: str) -> Agent:
    """Synthesize a placeholder Agent that owns every registered Tool.

    The aggregator is only used as input to ``agent_to_openapi`` so the
    runtime can return a single OpenAPI document covering every tool in
    the registry. The agent identity is a stable URN derived from the
    base URL so repeated calls produce stable output.
    """
    return Agent(
        id="urn:uap:agent:uap-runtime-aggregator",
        name="uap_runtime_aggregator",
        display_name="UAP Runtime — All Tools",
        description=(
            "Synthetic agent assembled by the UAP runtime so that every "
            "registered Tool can be exported in a single OpenAPI document."
        ),
        version=SDK_VERSION,
        tools=list(tools),
        capabilities=Capabilities(
            idempotent=False,
            side_effects=SideEffects.READ_ONLY,
            deterministic=False,
            requires_human_approval=False,
        ),
        compliance=Compliance(),
        tags=["uap", "runtime", "aggregator"],
        metadata={"base_url": base_url},
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def create_app(
    registry: Registry,
    *,
    base_url: str = "http://localhost:8000",
) -> "FastAPI":
    """Build a FastAPI app exposing ``registry`` over HTTP.

    The factory imports :mod:`fastapi` lazily so callers that never
    invoke it can still import this module without the runtime extra
    installed.

    Parameters
    ----------
    registry:
        Any object satisfying the :class:`Registry` protocol.
    base_url:
        Public URL where the runtime is reachable. Used to render
        absolute links in the ``/.well-known/agent.json`` index when
        multiple agents are registered.
    """
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:  # pragma: no cover - import guard
        raise ImportError(
            "FastAPI is required to use unifiedagentprotocol.runtime. "
            "Install with: pip install 'unified-agent-protocol[runtime]' "
            "or: pip install fastapi"
        ) from exc

    app = FastAPI(
        title="Unified Agent Protocol Runtime",
        description=(
            "Read-only HTTP surface for a UAP registry. Serves UAP envelopes "
            "plus best-effort projections to A2A AgentCards, MCP tools, and "
            "OpenAPI."
        ),
        version=SDK_VERSION,
    )

    # ------------------------------------------------------------------
    # Liveness
    # ------------------------------------------------------------------

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {
            "status": "ok",
            "uap_version": UAP_VERSION,
            "sdk_version": SDK_VERSION,
        }

    # ------------------------------------------------------------------
    # /.well-known/agent.json
    # ------------------------------------------------------------------

    @app.get("/.well-known/agent.json")
    def well_known_agent() -> Dict[str, Any]:
        agents = _agents(registry)
        if len(agents) == 1:
            from unifiedagentprotocol.bridges.a2a import to_a2a

            card, _loss = to_a2a(agents[0])
            return card

        # Zero or multiple agents -> short directory listing.
        listed: List[Dict[str, Any]] = []
        for agent in agents:
            slug = _slug_of(agent.id)
            listed.append(
                {
                    "id": agent.id,
                    "name": agent.display_name or agent.name,
                    "url": f"{base_url.rstrip('/')}/agents/{slug}",
                }
            )
        return {"agents": listed}

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------

    @app.get("/agents")
    def list_agents() -> List[Dict[str, Any]]:
        return [_envelope(a) for a in _agents(registry)]

    @app.get("/agents/{slug}")
    def get_agent(slug: str) -> Dict[str, Any]:
        agent = _find_agent_by_slug(registry, slug)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")
        return _envelope(agent)

    @app.get("/agents/{slug}/.well-known/agent.json")
    def agent_well_known(slug: str) -> Dict[str, Any]:
        agent = _find_agent_by_slug(registry, slug)
        if agent is None:
            raise HTTPException(status_code=404, detail=f"Agent '{slug}' not found")
        from unifiedagentprotocol.bridges.a2a import to_a2a

        card, _loss = to_a2a(agent)
        return card

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @app.get("/tools")
    def list_tools() -> List[Dict[str, Any]]:
        return [_envelope(t) for t in _tools(registry)]

    @app.get("/tools/{slug}")
    def get_tool(slug: str) -> Dict[str, Any]:
        tool = _find_tool_by_slug(registry, slug)
        if tool is None:
            raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
        return _envelope(tool)

    # ------------------------------------------------------------------
    # Manifests
    # ------------------------------------------------------------------

    @app.get("/manifests")
    def list_manifests() -> List[Dict[str, Any]]:
        return [_envelope(m) for m in _manifests(registry)]

    # ------------------------------------------------------------------
    # MCP projection
    # ------------------------------------------------------------------

    @app.get("/mcp/tools")
    def mcp_tools() -> List[Dict[str, Any]]:
        from unifiedagentprotocol.bridges.mcp import tool_to_mcp

        out: List[Dict[str, Any]] = []
        for tool in _tools(registry):
            try:
                mcp_tool, _loss = tool_to_mcp(tool)
            except Exception:
                # The /mcp/tools endpoint is best-effort: skip individual
                # tools that cannot be projected rather than failing the
                # whole listing.
                continue
            out.append(mcp_tool)
        return out

    # ------------------------------------------------------------------
    # OpenAPI projection
    # ------------------------------------------------------------------

    @app.get("/openapi-uap.json")
    def openapi_uap() -> Dict[str, Any]:
        try:
            from unifiedagentprotocol.bridges.openapi import agent_to_openapi
        except ImportError as exc:
            raise HTTPException(
                status_code=501,
                detail=(
                    "OpenAPI bridge is not installed; "
                    "cannot project tools to OpenAPI."
                ),
            ) from exc

        aggregator = _aggregator_agent(_tools(registry), base_url=base_url)
        result = agent_to_openapi(aggregator)
        # Bridges return (doc, LossInfo) tuples; tolerate either shape so
        # this code keeps working as the bridge matures.
        if isinstance(result, tuple) and result:
            doc = result[0]
        else:
            doc = result
        return doc

    return app


__all__ = ["create_app"]
