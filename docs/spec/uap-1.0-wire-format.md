# UAP 1.0 — Wire Format Specification

**Status:** Draft Standard
**Version:** 1.0.0
**License:** Apache-2.0

## 1. Envelope

Every UAP payload (whether a single `Tool`, a single `Agent`, or a
`Manifest`) is wrapped in an envelope:

```json
{
  "uap_version": "1.0",
  "kind": "agent",            // "agent" | "tool" | "manifest"
  "id": "urn:uap:agent:weather-bot",
  "payload": { /* type-specific */ },
  "signature": null,           // optional Ed25519 signature
  "produced_by": "uap-core/1.0.0"
}
```

## 2. Identity

Every `Tool`, `Agent`, and `Manifest` MUST carry a globally unique `id`
in URN form: `urn:uap:<kind>:<slug>` (slug = RFC 5234 unreserved,
lowercase). Optionally a `uri` for HTTP-resolvable instances.

### 2.1 Runtime task envelope

A persistent A2A runtime MAY accept the governed `agent.task` message defined by
`unifiedagentprotocol.runtime.TaskEnvelope`. It is distinct from the definition
`Envelope`: the message adds an approved `connection_id`, external `tenant_id`,
nonce and short expiry. Its `id` is `urn:uap:task:<slug>` and its Ed25519 signature
covers `canonical_statement()` (all routing/security fields plus the bounded task
payload, excluding the signature). Receivers MUST bind the connection to a stored
producer URN, tenant, public key and endpoint allowlist, persist the nonce before
acceptance, and reject unknown fields. A valid signature alone never grants auto-start.

## 3. Versioning

- `uap_version`: the wire-format version (this document).
- `version`: the semantic version of the *content* (a Tool/Agent
  definition), independent of the wire version.

## 4. Core Types

### 4.1 `Parameter`

A `Parameter` is a strict subset of JSON Schema Draft 2020-12, plus UAP
extensions namespaced under `x-uap-*`:

```json
{
  "name": "city",
  "schema": {
    "type": "string",
    "description": "Target city",
    "minLength": 1,
    "maxLength": 100,
    "x-uap-sensitive": false,
    "x-uap-pii": "none"
  },
  "required": true,
  "location": "body"           // "body" | "query" | "path" | "header" | "context"
}
```

### 4.2 `Tool`

```json
{
  "id": "urn:uap:tool:get-weather",
  "name": "get_weather",
  "display_name": "Get Weather",
  "description": "...",
  "version": "1.2.0",
  "parameters": [ /* Parameter[] */ ],
  "output": { "schema": { /* JSON Schema */ } },
  "endpoint": { /* Endpoint */ },
  "triggers": [ /* Trigger[] */ ],
  "auth": { /* AuthConfig | null */ },
  "capabilities": { /* Capabilities */ },
  "compliance": { /* Compliance */ },
  "cost": { /* CostHint | null */ },
  "ui": { /* UIConfig | null */ },
  "tags": ["weather", "public"],
  "metadata": { /* string -> any */ }
}
```

### 4.3 `Agent`

```json
{
  "id": "urn:uap:agent:weather-bot",
  "name": "WeatherBot",
  "display_name": "Weather Bot",
  "description": "...",
  "version": "1.0.0",
  "tools": [ /* Tool[] or Tool URN refs */ ],
  "skills": [ /* Skill[] */ ],
  "endpoints": [ /* Endpoint[] */ ],
  "auth": { /* AuthConfig | null */ },
  "capabilities": { /* Capabilities */ },
  "compliance": { /* Compliance */ },
  "ui": { /* UIConfig | null */ },
  "tags": ["weather"],
  "metadata": { /* string -> any */ }
}
```

### 4.4 `Endpoint`

```json
{
  "transport": "http",         // "http" | "sse" | "websocket" | "stdio" | "grpc"
  "url": "https://api.example.com/weather",
  "method": "POST",            // HTTP only
  "streaming": false,
  "supports_async": false
}
```

### 4.5 `AuthConfig`

```json
{
  "type": "oauth2",            // "none" | "api_key" | "bearer" | "oauth2" | "mtls" | "aws_sigv4"
  "scopes": ["read:weather"],
  "token_url": "https://auth.example.com/token",
  "secret_ref": "vault://kv/data/weather-api#token"   // never inline secrets
}
```

### 4.6 `Capabilities`

```json
{
  "idempotent": true,
  "side_effects": "read_only", // "none" | "read_only" | "writes" | "destructive"
  "deterministic": true,
  "requires_human_approval": false,
  "long_running": false,
  "supports_streaming": false,
  "supports_cancellation": false
}
```

### 4.7 `Compliance`

```json
{
  "data_classification": "public",  // "public" | "internal" | "confidential" | "restricted"
  "pii": "none",                    // "none" | "low" | "high"
  "regulations": ["GDPR"],          // ISO list: GDPR, HIPAA, SOC2, PCI-DSS, …
  "data_residency": ["EU"],         // ISO country/region codes
  "retention_days": null
}
```

### 4.8 `CostHint`

```json
{
  "currency": "USD",
  "per_call_usd": 0.0001,
  "tokens_in_estimate": null,
  "tokens_out_estimate": null,
  "latency_ms_p50": 200,
  "latency_ms_p99": 1500
}
```

### 4.9 `Trigger`

```json
{
  "type": "cron",              // "manual" | "cron" | "webhook" | "intent" | "event"
  "cron": "0 */6 * * *",       // when type=cron
  "intent_pattern": "^/weather", // when type=intent
  "webhook_path": "/hooks/x",  // when type=webhook
  "event_name": null,          // when type=event
  "description": null
}
```

### 4.10 `UIConfig`

```json
{
  "label": "Get Weather",
  "description": null,
  "icon": "mdi:weather-partly-cloudy",
  "color": "#00aaff",
  "group": "weather",
  "order": 10
}
```

## 5. Manifest (Registry payload)

```json
{
  "uap_version": "1.0",
  "kind": "manifest",
  "id": "urn:uap:manifest:weather-suite",
  "name": "Weather Suite",
  "description": "Bundled weather tools and agents",
  "version": "1.0.0",
  "agents": [ /* Agent[] or URN refs */ ],
  "tools": [ /* Tool[] or URN refs */ ],
  "publisher": "WhoMeta",
  "homepage": "https://www.whometa.io",
  "license": "Apache-2.0"
}
```

## 6. Bridges

Every bridge SHIPS two functions:

- `to_<format>(uap_obj) -> (foreign_obj, LossInfo)`
- `from_<format>(foreign_obj) -> (uap_obj, LossInfo)`

A bridge is **certified** only when:

1. It is round-trip stable on the bridge's test corpus.
2. It declares `LossInfo` for every dropped field.
3. It targets a publicly versioned external spec.

## 7. LossInfo

```json
{
  "dropped_fields": ["compliance.retention_days"],
  "coerced_fields": ["parameters[0].schema.format"],
  "notes": ["A2A AgentCard does not model retention; field discarded."]
}
```

## 8. Reserved extension prefix

All custom fields MUST be prefixed with `x-`. The `x-uap-*` namespace is
reserved for this specification.
