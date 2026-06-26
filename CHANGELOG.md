# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-06-26

Stable SDK release (UAP wire format 1.0). Version bumped from the
premature PyPI `1.0.1` alpha to publish the ground-up rebuild.

## [1.0.0] — 2026-06-04

This is a ground-up rebuild and the first **stable** release.
The pre-1.0 SDK is removed.

### Added — Core IR
- Pydantic v2-native models: `Tool`, `Agent`, `Skill`, `Manifest`,
  `Envelope`, `Parameter`, `ParameterSchema`.
- Enterprise layer: `AuthConfig` (none/api_key/bearer/oauth2/mtls/sigv4/gcp_sa)
  with mandatory external `secret_ref`, `Capabilities` (idempotent,
  side_effects, deterministic, requires_human_approval, …), `Compliance`
  (data_classification, pii, regulations, data_residency, retention_days),
  `CostHint` (per-call USD, latency p50/p99, tokens).
- Endpoint/Transport (http/sse/websocket/stdio/grpc/nats), Trigger
  (manual/cron/webhook/intent/event) with consistency validation,
  UIConfig, LossInfo.
- URN-based identity (`urn:uap:{kind}:{slug}`), validated.
- Versioned wire `Envelope` with compatibility check.
- Canonical JSON Schemas under `schemas/uap/1.0/`.

### Added — Bridges (all bidirectional, all with LossInfo)
- **MCP** — Tool ↔ MCP function; Agent ↔ MCP server descriptor.
- **A2A** — Agent ↔ AgentCard.
- **OpenAI** — Tool ↔ function tool; Agent ↔ Assistant.
- **Anthropic** — Tool ↔ Anthropic tool-use spec.
- **Gemini** — Tool ↔ Function Declaration (uppercase types).
- **OpenAPI 3** — Agent ↔ OpenAPI spec; UAP fields preserved via
  `x-uap-*` extensions for lossless round-trip.
- **Swagger 2** — Agent ↔ Swagger 2 doc.
- **OpenWebUI** — Tool ↔ OpenWebUI tool JSON.
- **LangChain** — Tool ↔ LangChain dict spec.

### Added — Registry & Runtime (optional extras)
- `InMemoryRegistry`, `FilesystemRegistry` (atomic writes, persistent).
- FastAPI runtime adapter with `/.well-known/agent.json`,
  `/agents`, `/tools`, `/manifests`, `/mcp/tools`, `/openapi-uap.json`,
  `/healthz`.

### Added — CLI
- `uap bind` (multi-format auto-detect + LossInfo),
  `uap validate`, `uap lint`, `uap schema-export`,
  `uap version`, `uap serve`.

### Added — Quality
- CI (GitHub Actions) running tests on Python 3.10/3.11/3.12.
- Ruff lint, mypy advisory.
- Bridge round-trip test suites.
- Schema-sync verification (regenerated schemas must match committed).

### Removed
- The pre-1.0 stub modules `models/`, `parser/`, `export/`,
  the unused `requests`, `rich`, `pyyaml` hard-deps,
  the empty `play.json` and `registry/builtin_types.json`.
- Pydantic v1 syntax everywhere.

### Breaking
- Wire format is now versioned (`uap_version: "1.0"`); pre-1.0 dumps
  cannot be loaded directly. Use `uap bind --format uap` to upconvert.
- `Tool.parameters` now contain a JSON-Schema `ParameterSchema` instead
  of an unconstrained string type.
- All IDs are URNs.

## [0.1.0] — 2025-06-20 (deprecated)

Initial alpha. Removed in 1.0.
