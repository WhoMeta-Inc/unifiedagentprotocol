# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP CLI — bind, validate, lint, schema-export, serve, registry.

Run with:

    uap --help

The CLI is intentionally thin: it dispatches to the bridges and the
runtime/registry packages. Heavy logic lives in the libraries, not here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

import typer

from unifiedagentprotocol import (
    Agent,
    Envelope,
    Kind,
    LossInfo,
    Manifest,
    SDK_VERSION,
    Tool,
    UAP_VERSION,
)

app = typer.Typer(
    add_completion=False,
    help="Unified Agent Protocol CLI — convert, validate, serve.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_FORMATS = (
    "mcp",
    "a2a",
    "openai",
    "anthropic",
    "gemini",
    "openapi",
    "swagger",
    "openwebui",
    "langchain",
)


def _read_input(path: Path) -> Any:
    text = path.read_text()
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as e:
            raise typer.BadParameter(
                "PyYAML required for YAML input; install with 'pip install pyyaml'"
            ) from e
        return yaml.safe_load(text)
    return json.loads(text)


def _write_output(data: Any, output: Optional[Path]) -> None:
    payload = json.dumps(data, indent=2, sort_keys=False)
    if output:
        output.write_text(payload + "\n")
    else:
        typer.echo(payload)


def _detect_and_parse(data: Any) -> Any:
    """Heuristic auto-detection of input format → UAP object."""
    # OpenAPI v3
    if isinstance(data, dict) and str(data.get("openapi", "")).startswith("3"):
        from unifiedagentprotocol.bridges.openapi import from_openapi

        obj, _ = from_openapi(data)
        return obj
    # Swagger v2
    if isinstance(data, dict) and data.get("swagger") == "2.0":
        from unifiedagentprotocol.bridges.swagger import from_swagger

        obj, _ = from_swagger(data)
        return obj
    # MCP server descriptor
    if isinstance(data, dict) and "tools" in data and "name" in data and (
        "resources" in data or "prompts" in data
    ):
        from unifiedagentprotocol.bridges.mcp import from_mcp

        obj, _ = from_mcp(data)
        return obj
    # A2A AgentCard
    if isinstance(data, dict) and "defaultInputModes" in data and "skills" in data:
        from unifiedagentprotocol.bridges.a2a import from_a2a

        obj, _ = from_a2a(data)
        return obj
    # OpenAI function tool
    if isinstance(data, dict) and data.get("type") == "function" and "function" in data:
        from unifiedagentprotocol.bridges.openai import from_openai

        obj, _ = from_openai(data)
        return obj
    # Anthropic tool
    if isinstance(data, dict) and "input_schema" in data and "name" in data:
        from unifiedagentprotocol.bridges.anthropic import from_anthropic

        obj, _ = from_anthropic(data)
        return obj
    # OpenWebUI
    if isinstance(data, dict) and ("returns" in data or "parameters" in data) and (
        "id" in data or "name" in data
    ):
        from unifiedagentprotocol.bridges.openwebui import from_openwebui

        obj, _ = from_openwebui(data)
        return obj
    # UAP envelope
    if isinstance(data, dict) and "uap_version" in data and "payload" in data:
        env = Envelope.model_validate(data)
        return env.payload
    # Plain Tool / Agent / Manifest
    if isinstance(data, dict) and "id" in data:
        urn = str(data["id"])
        if urn.startswith("urn:uap:tool:"):
            return Tool.model_validate(data)
        if urn.startswith("urn:uap:agent:"):
            return Agent.model_validate(data)
        if urn.startswith("urn:uap:manifest:"):
            return Manifest.model_validate(data)
    raise typer.BadParameter("Could not auto-detect input format.")


def _convert(obj: Any, fmt: str) -> tuple[Any, LossInfo]:
    if fmt == "mcp":
        from unifiedagentprotocol.bridges.mcp import to_mcp

        return to_mcp(obj)
    if fmt == "a2a":
        from unifiedagentprotocol.bridges.a2a import to_a2a

        return to_a2a(obj)
    if fmt == "openai":
        from unifiedagentprotocol.bridges.openai import to_openai

        return to_openai(obj)
    if fmt == "anthropic":
        from unifiedagentprotocol.bridges.anthropic import to_anthropic

        return to_anthropic(obj)
    if fmt == "gemini":
        from unifiedagentprotocol.bridges.gemini import to_gemini

        return to_gemini(obj)
    if fmt == "openapi":
        from unifiedagentprotocol.bridges.openapi import to_openapi

        return to_openapi(obj)
    if fmt == "swagger":
        from unifiedagentprotocol.bridges.swagger import to_swagger

        return to_swagger(obj)
    if fmt == "openwebui":
        from unifiedagentprotocol.bridges.openwebui import to_openwebui

        return to_openwebui(obj)
    if fmt == "langchain":
        from unifiedagentprotocol.bridges.langchain import to_langchain

        return to_langchain(obj)
    if fmt == "uap":
        if isinstance(obj, (Tool, Agent, Manifest)):
            return Envelope.of(obj).to_wire(), LossInfo()
        return obj, LossInfo()
    raise typer.BadParameter(f"Unknown format {fmt!r}. Allowed: {_FORMATS} or 'uap'.")


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

@app.command()
def bind(
    input: Path = typer.Option(..., exists=True, help="Input definition (json/yaml)"),
    format: str = typer.Option(
        "uap", help=f"Target format. One of {(*_FORMATS, 'uap')}"
    ),
    output: Optional[Path] = typer.Option(None, help="Write result to file"),
    show_loss: bool = typer.Option(False, help="Print LossInfo to stderr"),
) -> None:
    """Convert an input definition to the requested target format."""
    data = _read_input(input)
    obj = _detect_and_parse(data)
    result, loss = _convert(obj, format)
    _write_output(result, output)
    if show_loss and loss.is_lossy():
        typer.echo(
            "LossInfo: " + json.dumps(loss.model_dump(), indent=2),
            err=True,
        )


@app.command()
def validate(
    input: Path = typer.Option(..., exists=True, help="UAP envelope or payload"),
) -> None:
    """Validate a UAP payload against the v1.0 schema."""
    data = _read_input(input)
    if isinstance(data, dict) and "uap_version" in data and "payload" in data:
        Envelope.model_validate(data)
    else:
        _detect_and_parse(data)
    typer.echo("OK")


@app.command()
def lint(
    input: Path = typer.Option(..., exists=True, help="UAP definition file"),
) -> None:
    """Validate plus surface common quality warnings."""
    data = _read_input(input)
    obj = _detect_and_parse(data)
    warnings: list[str] = []
    if isinstance(obj, Tool):
        if not obj.description or len(obj.description) < 10:
            warnings.append("Tool.description is short (<10 chars).")
        if obj.endpoint is None:
            warnings.append("Tool has no endpoint — not invocable as-is.")
        if obj.auth is None:
            warnings.append("Tool has no AuthConfig — defaulting to 'none'.")
    if isinstance(obj, Agent):
        if not obj.skills:
            warnings.append("Agent has no skills — A2A export will be empty.")
        if not obj.endpoints:
            warnings.append("Agent has no endpoints — A2A export needs a URL.")
    for w in warnings:
        typer.echo(f"warning: {w}", err=True)
    typer.echo(f"OK ({len(warnings)} warning(s))")


@app.command("schema-export")
def schema_export(
    output_dir: Path = typer.Option(
        Path("schemas/uap/1.0"),
        help="Directory to write JSON Schemas into.",
    ),
) -> None:
    """Emit JSON Schemas for Envelope / Agent / Tool / Manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = {
        "envelope.schema.json": Envelope,
        "agent.schema.json": Agent,
        "tool.schema.json": Tool,
        "manifest.schema.json": Manifest,
    }
    for filename, model in targets.items():
        schema = model.model_json_schema(by_alias=True)
        schema["$id"] = f"https://schemas.whometa.io/uap/1.0/{filename}"
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (output_dir / filename).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n"
        )
    typer.echo(f"Wrote {len(targets)} schema(s) to {output_dir}")


@app.command()
def version() -> None:
    """Print UAP wire version and SDK version."""
    typer.echo(json.dumps({"uap_version": UAP_VERSION, "sdk_version": SDK_VERSION}))


@app.command()
def serve(
    registry_path: Optional[Path] = typer.Option(
        None,
        help="Filesystem registry root. If unset, uses an empty in-memory registry.",
    ),
    host: str = typer.Option("127.0.0.1"),
    port: int = typer.Option(8000),
) -> None:
    """Start a FastAPI runtime exposing the registry."""
    try:
        import uvicorn  # type: ignore
    except ImportError as e:
        typer.echo(
            "uvicorn is required: pip install unified-agent-protocol[runtime]",
            err=True,
        )
        raise typer.Exit(code=1) from e

    from unifiedagentprotocol.registry_impl import (
        FilesystemRegistry,
        InMemoryRegistry,
    )
    from unifiedagentprotocol.runtime import create_app

    reg = (
        FilesystemRegistry(registry_path)
        if registry_path is not None
        else InMemoryRegistry()
    )
    app_inst = create_app(reg, base_url=f"http://{host}:{port}")
    uvicorn.run(app_inst, host=host, port=port)


@app.callback()
def _main() -> None:
    """Unified Agent Protocol CLI."""


if __name__ == "__main__":  # pragma: no cover
    sys.exit(app())
