# Unified Agent Protocol (UAP) – Core SDK Specification

**Version**: 0.1 Alpha  
**Maintained by**: [WhoMeta Labs part of WhoMeta Inc.](https://www.whometa.io)  
**License**: Apache 2.0  
**Language**: Python 3.10+  
**Repository**: _Private/internal (planned public release Q3 2025)_

---
[![OpenHub](https://www.openhub.net/p/uap/widgets/project_thin_badge.gif)](https://www.openhub.net/p/uap)
---

## ✨ Introduction

The **Unified Agent Protocol (UAP)** is a foundational interoperability layer designed to **standardize the definition, registration, execution, and orchestration of AI agents and tools** across diverse ecosystems.  
UAP is **not** a runtime or a competing protocol like A2A or MCP – instead, it acts as a **universal adapter**, enabling seamless translation between heterogeneous agent formats, toolkits, and interface protocols.

The `uap-core` SDK is the **reference Python implementation** of this protocol, designed for SDK-level integration, automatic conversions, and full schema introspection.

---

## 💡 Motivation

As the AI agent ecosystem evolves, developers face increasing friction when integrating tools across platforms like OpenWebUI, LangChain, Azure OpenAI Agents, OpenAPI-based agents, or proprietary agent chains.

Common challenges include:

- ❌ Fragmented agent and tool definition formats
- ❌ Missing bridges between proprietary agent runtimes
- ❌ Lack of universal abstraction for tool metadata, input types, and execution capabilities
- ❌ Friction when reusing agent definitions across platforms (e.g., MCP ↔ A2A ↔ OpenAPI)

**UAP solves this** by introducing a **common schema + protocol** that allows agents and tools to be described once – and deployed, registered, or bridged anywhere.

---

## 📦 Key Features (Milestone 1)

- 🧠 **Unified JSON model**: All agent, tool, trigger, and role definitions follow a strongly typed Pydantic schema.
- 🔌 **Multi-source parsers**:
  - `parse_openwebui(json)`: Import tools from OpenWebUI format.
  - `parse_langchain(tool)`: Extract tool metadata from LangChain definitions.
  - `parse_openapi(spec)`: Map OpenAPI endpoints to UAP tools.
- 📤 **Export bridges**:
  - `to_a2a(agent)`: Generate A2A-compatible payload.
  - `to_mcp(agent)`: Convert to Model Context Protocol (MCP) schema.
  - `to_openapi(tool)`: Derive standard OpenAPI spec from UAP tool.
- 🖥️ **CLI (`uap bind`)**:
  - Run transformations via command-line: `uap bind --input tools.json --format mcp`
- 🛠️ **Development-first SDK**:
  - Works offline, no server required.
  - Fully typed Python models (intellisense, validation).
  - Optional integration with LangChain, FastAPI, and asyncio runtimes.

---

## 🧩 Core Concepts

| Concept        | Description                                                                 |
|----------------|-----------------------------------------------------------------------------|
| `Tool`         | Describes an executable unit with input/output schemas and runtime hints.  |
| `Agent`        | A logical actor using one or more tools to fulfill a task or objective.    |
| `Trigger`      | Defines when and how agents/tools should activate (event, cron, intent).   |
| `Role`         | Describes access & behavioral context (e.g., "analyst", "investigator").   |
| `OutputSchema` | Optional structure for results / downstream usage.                         |
| `UIConfig`     | Describes how this entity is represented in GUIs (forms, widgets, prompts).|

All objects are implemented as subclasses of `pydantic.BaseModel` and support:

- ✅ Full JSON validation
- ✅ `.dict()` / `.json()` / `.from_json()` compatibility
- ✅ Versioning fields
- ✅ Extension-safe typing (e.g., `extra = "allow"`)

---

## 🔄 Ecosystem Bridges

| Target Protocol | Bridge | Status | Description |
|-----------------|--------|--------|-------------|
| A2A (Agent-to-Agent) | `to_a2a()` | ✅ | Convert UAP agent into valid A2A descriptor |
| MCP (Model Context Protocol) | `to_mcp()` | ✅ | Map UAP agent/tool into MCP-compliant schema |
| OpenAPI 3 | `to_openapi()` | ✅ | Export UAP tool(s) as OpenAPI endpoints |

These bridges allow **inter-protocol operability** – for example, developers can register a LangChain tool on OpenWebUI and then expose it in an A2A runtime via UAP translation.

---

## 📚 Example Use Case

```bash
# Convert OpenWebUI tools into MCP-ready format
uap bind --input tools_openwebui.json --format mcp > mcp_payload.json
```  

---

## 🤝 Contributing

Contributions, issues and feature requests are **very welcome**!

1. Fork the repository
2. Create your feature branch (`git checkout -b feat/awesome-feature`)
3. Commit your changes (`git commit -m 'feat: add awesome feature'`)
4. Push to the branch (`git push origin feat/awesome-feature`)
5. Open a pull request

For full guidelines, please read the [CONTRIBUTE guide](contribute.md).

---

## ⚖️ License

This project is licensed under the **Apache License 2.0** – see the [LICENSE](LICENSE) file for details.

---

## 📑 Changelog

All notable changes will be documented in [CHANGELOG.md](CHANGELOG.md).
