# Unified Agent Protocol (UAP) — Core SDK

**Version 1.0** · Apache-2.0 · Python 3.10+

UAP is the **universal interoperability layer** for AI agents and tools.

Define an agent **once** in UAP — then ship it to **MCP**, **A2A**,
**OpenAI Assistants**, **Anthropic Tool Use**, **Google Gemini
Functions**, **OpenAPI 3**, **OpenWebUI**, **LangChain** — without
rewriting a single field. Every adapter is **bidirectional** and
declares its **LossInfo** explicitly. No silent data loss.

## What UAP gives you over MCP / A2A alone

| Concern | MCP | A2A | UAP |
|---------|:---:|:---:|:---:|
| Tool description schema | ✅ | — | ✅ |
| Agent-to-Agent runtime | — | ✅ | ✅ (via bridges) |
| Cross-vendor bridges | — | — | ✅ (9 formats) |
| Bidirectional round-trip | — | — | ✅ |
| Auth modelling (OAuth2/mTLS/SigV4/…) | partial | partial | ✅ |
| RBAC / Capabilities | — | — | ✅ |
| Compliance (GDPR/HIPAA/residency) | — | — | ✅ |
| Cost / latency hints | — | — | ✅ |
| URN identity | — | — | ✅ |
| Versioned wire format | ✅ | ✅ | ✅ |

## Install

```bash
pip install unified-agent-protocol            # core SDK only
pip install unified-agent-protocol[runtime]   # + FastAPI runtime
pip install unified-agent-protocol[all]       # + every optional dep
```

## Quick start

```python
from unifiedagentprotocol import (
    Tool, Agent, Skill, Parameter, ParameterSchema,
    Capabilities, SideEffects, Compliance, DataClassification,
    AuthConfig, AuthType, Endpoint, Transport, Envelope,
)

weather = Tool(
    id="urn:uap:tool:get-weather",
    name="get_weather",
    description="Return current weather for a city.",
    parameters=[Parameter(name="city", schema=ParameterSchema(type="string"))],
    endpoint=Endpoint(transport=Transport.HTTP,
                      url="https://api.example.com/weather", method="POST"),
    auth=AuthConfig(type=AuthType.API_KEY,
                    secret_ref="vault://kv/data/weather#token"),
    capabilities=Capabilities(idempotent=True,
                              side_effects=SideEffects.READ_ONLY,
                              deterministic=False,
                              requires_human_approval=False),
    compliance=Compliance(data_classification=DataClassification.PUBLIC,
                          regulations=["GDPR"], data_residency=["EU"]),
)

agent = Agent(
    id="urn:uap:agent:weather-bot",
    name="WeatherBot",
    description="Provides weather information.",
    tools=[weather],
    skills=[Skill(id="answer-weather", name="answer-weather",
                  description="Answer weather questions.")],
    endpoints=[Endpoint(transport=Transport.HTTP, url="https://bot.example.com")],
)

print(Envelope.of(agent).to_wire())
```

Ship it to every ecosystem:

```python
from unifiedagentprotocol.bridges.mcp        import to_mcp
from unifiedagentprotocol.bridges.a2a        import to_a2a
from unifiedagentprotocol.bridges.openai     import to_openai
from unifiedagentprotocol.bridges.anthropic  import to_anthropic
from unifiedagentprotocol.bridges.gemini     import to_gemini
from unifiedagentprotocol.bridges.openapi    import to_openapi

mcp_payload,    _ = to_mcp(agent)
a2a_card,       _ = to_a2a(agent)
oai_assistant,  _ = to_openai(agent)
claude_tool,    _ = to_anthropic(weather)
gemini_decl,    _ = to_gemini(weather)
openapi_spec,   _ = to_openapi(agent)
```

Every bridge also has an inverse `from_<format>(…)` returning
`(uap_object, LossInfo)`.

## CLI

```bash
uap version
uap schema-export --output-dir schemas/uap/1.0
uap bind  --input my_tool.json --format mcp --show-loss
uap validate --input my_agent.json
uap lint --input my_agent.json
uap serve --registry-path ./registry --port 8000
```

The auto-detect `bind` accepts MCP, A2A, OpenAI, Anthropic, OpenWebUI,
LangChain, OpenAPI 3, Swagger 2 and bare UAP envelopes.

## Governed directory matching

The optional runtime includes a side-effect-free matcher for applications that
project tenant, availability, capacity and evaluation data into UAP Agent
metadata:

```python
from unifiedagentprotocol.runtime import match_agents

candidates = match_agents(
    registry,
    tenant_id="tenant-a",
    required_capabilities=["research", "evidence"],
    delegation_chain=["urn:uap:agent:requester"],
)
```

Matching fails closed for missing tenant/availability/capacity metadata, avoids
agents already in the delegation chain, and excludes external agents unless
they are both explicitly requested and marked approved. It does not create a
task or open an external boundary; the embedding application remains
responsible for authorization, budget/HITL policy and source-owned audit.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Runtime  (optional)   FastAPI adapter, /.well-known/agent   │
├──────────────────────────────────────────────────────────────┤
│  Registry (optional)   In-memory / Filesystem / pluggable    │
├──────────────────────────────────────────────────────────────┤
│  Bridges               MCP, A2A, OpenAI, Anthropic, Gemini,  │
│  (bidirectional)       OpenAPI, Swagger, OpenWebUI, LangChain│
├──────────────────────────────────────────────────────────────┤
│  Core IR (Schema)      Tool, Agent, Parameter (JSON-Schema), │
│                        Auth, Capabilities, Compliance, Cost, │
│                        Endpoint, Trigger, Envelope, LossInfo │
├──────────────────────────────────────────────────────────────┤
│  Wire Spec             schemas/uap/1.0/*.schema.json         │
└──────────────────────────────────────────────────────────────┘
```

Layer rules:

- `core/` depends on nothing but Pydantic + stdlib.
- `bridges/<x>/` depends only on `core/`.
- `runtime/` depends on `core/`, `bridges/`, `registry_impl/`.
- `cli/` is the only module allowed to import anywhere.

See [`docs/adr/0001-architecture-overview.md`](docs/adr/0001-architecture-overview.md)
and [`docs/spec/uap-1.0-wire-format.md`](docs/spec/uap-1.0-wire-format.md).

## Examples

- [`examples/01_define_tool_and_agent.py`](examples/01_define_tool_and_agent.py) — full enterprise-marked agent.
- [`examples/02_bridge_to_many_formats.py`](examples/02_bridge_to_many_formats.py) — same agent → six target formats.

## Testing

```bash
pytest -q
```

Bridge round-trip tests live under `tests/bridges/` and assert
`from_x(to_x(obj)) == obj` on the representable subset, with
`LossInfo` covering the rest.

## License

Apache 2.0 — see [LICENSE](LICENSE).
