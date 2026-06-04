# ADR 0001 — UAP v1.0 Architecture Overview

**Status:** Accepted
**Date:** 2026-06-04
**Author:** CTO / WhoMeta Labs

## Context

UAP (Unified Agent Protocol) aims to be the universal interoperability layer
for AI agents and tools across heterogeneous ecosystems (A2A, MCP,
OpenAI Assistants, Anthropic Tool Use, Google Gemini Functions, LangChain,
OpenWebUI, OpenAPI, AutoGen, CrewAI, n8n, …).

The pre-1.0 SDK was a thin Pydantic wrapper with stub exporters. v1.0 is a
ground-up rebuild positioning UAP as a **canonical IR (intermediate
representation) plus a network of bidirectional bridges**, with an
**enterprise envelope** (auth, capabilities, compliance, cost) and an
optional **registry + runtime**.

## Decision

UAP v1.0 is organized in five layers:

```
┌────────────────────────────────────────────────────────────────┐
│  Runtime  (optional)     FastAPI adapter, /.well-known/agent   │
├────────────────────────────────────────────────────────────────┤
│  Registry (optional)     In-memory / FS / pluggable backends   │
├────────────────────────────────────────────────────────────────┤
│  Bridges                 MCP, A2A, OpenAI, Anthropic, Gemini,  │
│  (bidirectional)         LangChain, OpenWebUI, OpenAPI, …      │
├────────────────────────────────────────────────────────────────┤
│  Core IR (Schema)        Tool, Agent, Parameter (JSON-Schema), │
│                          Auth, Capabilities, Compliance, Cost, │
│                          Endpoint, Trigger, Envelope, LossInfo │
├────────────────────────────────────────────────────────────────┤
│  Wire Spec               JSON Schema files in schemas/uap/1.0/ │
│  (source of truth)       Pydantic models conform to them       │
└────────────────────────────────────────────────────────────────┘
```

## Principles

1. **Schema is the source of truth, code conforms.** JSON Schema files in
   `schemas/uap/<version>/` define the wire format. Pydantic models are
   the SDK representation but must validate against the JSON Schema.
2. **Versioned wire format.** Every payload carries `uap_version`. Bridges
   may reject unknown versions; the SDK ships migration helpers between
   adjacent versions.
3. **Bidirectional bridges only.** Every adapter ships both `to_<x>` and
   `from_<x>`. Round-trip tests (`from_x(to_x(uap)) == uap` modulo
   declared loss) are required for merge.
4. **LossInfo is explicit, never silent.** Conversions return a
   `LossInfo` companion object listing dropped or coerced fields.
5. **Enterprise layer is first-class, not optional.** Auth, capabilities,
   compliance, cost and SLA fields live in core, not in extensions.
6. **SDK works offline.** The core SDK has no network dependency.
   Registry and Runtime are opt-in extras.
7. **Plugin architecture.** Third parties can ship bridges/registries
   without forking the core (Python entry-points).

## Layering rules

- `core/` never imports from `bridges/`, `registry_impl/`, `runtime/`.
- `bridges/<name>/` may only depend on `core/` and stdlib.
- `runtime/` may depend on `core/`, `bridges/`, `registry_impl/`.
- `cli/` is the only module allowed to import anywhere.

## Backwards compatibility

The pre-1.0 modules (`models/`, `parser/`, `export/`) are removed and
replaced. UAP was pre-1.0, so SemVer permits the break. v1.0 is the first
stable contract.

## Consequences

- Schema becomes a publishable artifact (`schemas.whometa.io/uap/1.0`).
- Round-trip discipline gives UAP a defensible quality claim vs. ad-hoc
  conversion scripts.
- Enterprise fields make UAP attractive as a procurement-time standard,
  not just a developer convenience.
