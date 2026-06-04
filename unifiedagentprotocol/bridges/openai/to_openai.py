# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP -> OpenAI tool / Assistants v2 conversion.

OpenAI's function-tool schema is a strict subset of UAP. Most of the
enterprise envelope (auth, capabilities, compliance, cost, triggers,
endpoint) has no native home and is therefore declared as ``LossInfo``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Union

from unifiedagentprotocol.core import (
    Agent,
    LossInfo,
    Parameter,
    ParameterLocation,
    Tool,
)


def _parameter_schema_dict(param: Parameter) -> Dict[str, Any]:
    """Serialize a Parameter's schema to a JSON-Schema-style dict."""
    data = param.schema_.model_dump(
        mode="json", exclude_none=True, by_alias=True
    )
    # Surface the Parameter-level description when the schema lacks one.
    if param.description and "description" not in data:
        data["description"] = param.description
    return data


def _parameters_to_json_schema(
    params: List[Parameter],
    loss: LossInfo,
) -> Dict[str, Any]:
    """Collapse a UAP Parameter list into one ``object`` JSON schema."""
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for idx, p in enumerate(params):
        if p.location is not ParameterLocation.BODY:
            loss.dropped_fields.append(f"parameters[{idx}].location")
            loss.notes.append(
                f"Parameter '{p.name}' location={p.location.value!r} cannot be "
                "expressed in an OpenAI function tool (only body params are "
                "supported); it was folded into the request body."
            )
        properties[p.name] = _parameter_schema_dict(p)
        if p.required:
            required.append(p.name)
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _record_tool_envelope_losses(tool: Tool, loss: LossInfo, prefix: str = "") -> None:
    """Record loss entries for UAP envelope fields OpenAI cannot represent."""
    p = f"{prefix}." if prefix else ""
    if tool.triggers:
        loss.dropped_fields.append(f"{p}triggers")
        loss.notes.append(
            "OpenAI function tools have no concept of triggers; the list was dropped."
        )
    if tool.endpoint is not None:
        loss.dropped_fields.append(f"{p}endpoint")
        loss.notes.append(
            "OpenAI function tools delegate invocation to the host; endpoint discarded."
        )
    if tool.auth is not None:
        loss.dropped_fields.append(f"{p}auth")
    # capabilities and compliance always serialize (defaults exist), so we
    # only record them if they diverge from the implicit defaults the caller
    # asked us to track. For round-trip purposes we always flag them.
    loss.dropped_fields.append(f"{p}capabilities")
    loss.dropped_fields.append(f"{p}compliance")
    if tool.cost is not None:
        loss.dropped_fields.append(f"{p}cost")
    if tool.ui is not None:
        loss.dropped_fields.append(f"{p}ui")
    if tool.tags:
        loss.dropped_fields.append(f"{p}tags")
    if tool.output is not None:
        loss.dropped_fields.append(f"{p}output")
        loss.notes.append(
            "OpenAI function tools do not declare output schemas; field dropped."
        )


def tool_to_openai_function(uap_tool: Tool) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP ``Tool`` into an OpenAI function-tool dict.

    The result is the wrapped form::

        {"type": "function", "function": {"name", "description", "parameters"}}

    suitable for direct inclusion in a Chat Completions / Responses
    ``tools`` array or an Assistants ``tools`` array.
    """
    loss = LossInfo()
    parameters_schema = _parameters_to_json_schema(uap_tool.parameters, loss)

    function_body: Dict[str, Any] = {
        "name": uap_tool.name,
        "description": uap_tool.description,
        "parameters": parameters_schema,
    }
    # Smuggle the UAP URN through metadata so the reverse direction can
    # recover identity; OpenAI ignores unknown function fields.
    function_body["metadata"] = {
        "uap_urn": uap_tool.id,
        "uap_version": uap_tool.version,
    }
    if uap_tool.display_name:
        function_body["metadata"]["uap_display_name"] = uap_tool.display_name

    _record_tool_envelope_losses(uap_tool, loss)
    return {"type": "function", "function": function_body}, loss


def _skills_to_instructions(agent: Agent) -> str:
    """Concatenate Skill descriptions into a single instructions block."""
    lines: List[str] = []
    if agent.description:
        lines.append(agent.description)
    if agent.skills:
        lines.append("")
        lines.append("Skills:")
        for s in agent.skills:
            lines.append(f"- {s.name}: {s.description}")
            for ex in s.examples:
                lines.append(f"    example: {ex}")
    return "\n".join(lines).strip()


def agent_to_openai_assistant(
    uap_agent: Agent,
) -> Tuple[Dict[str, Any], LossInfo]:
    """Convert a UAP ``Agent`` into an OpenAI Assistants v2 body dict.

    The Agent's URN is stored under ``metadata.uap_urn``. If the Agent
    metadata does not already provide ``instructions``, the description
    and skills are concatenated into the ``instructions`` field.
    """
    loss = LossInfo()
    md_in = dict(uap_agent.metadata or {})

    # Tools: only inline Tool objects can be expressed in OpenAI's tool list;
    # bare URN references go into metadata for the reverse trip.
    tools_out: List[Dict[str, Any]] = []
    tool_urn_refs: List[str] = []
    for idx, t in enumerate(uap_agent.tools):
        if isinstance(t, Tool):
            tool_dict, t_loss = tool_to_openai_function(t)
            tools_out.append(tool_dict)
            # Re-key tool losses under tools[i].
            for f in t_loss.dropped_fields:
                loss.dropped_fields.append(f"tools[{idx}].{f}" if f else f"tools[{idx}]")
            for f in t_loss.coerced_fields:
                loss.coerced_fields.append(f"tools[{idx}].{f}" if f else f"tools[{idx}]")
            loss.notes.extend(t_loss.notes)
        else:
            # URN string reference — OpenAI has no way to express this.
            tool_urn_refs.append(t)

    # Instructions: explicit override > metadata.instructions > skills+desc.
    explicit = md_in.pop("openai_instructions", None) or md_in.pop("instructions", None)
    instructions = explicit if explicit is not None else _skills_to_instructions(uap_agent)

    # Model: prefer metadata.openai_model, else fall back to a sane default.
    model = md_in.pop("openai_model", None) or "gpt-4o"

    # Build the metadata: preserve uap_urn for round-trip.
    metadata: Dict[str, Any] = {
        "uap_urn": uap_agent.id,
        "uap_version": uap_agent.version,
    }
    if tool_urn_refs:
        metadata["uap_tool_refs"] = tool_urn_refs
    if uap_agent.display_name:
        metadata["uap_display_name"] = uap_agent.display_name
    # Pass through any caller-supplied OpenAI metadata.
    for k, v in md_in.items():
        if k not in metadata:
            metadata[k] = v

    assistant: Dict[str, Any] = {
        "name": uap_agent.name,
        "description": uap_agent.description,
        "model": model,
        "instructions": instructions,
        "tools": tools_out,
        "metadata": metadata,
    }

    # Envelope losses — same fields as Tool, plus endpoints (plural).
    if uap_agent.endpoints:
        loss.dropped_fields.append("endpoints")
        loss.notes.append(
            "OpenAI Assistants have no endpoint list; UAP endpoints discarded."
        )
    if uap_agent.auth is not None:
        loss.dropped_fields.append("auth")
    loss.dropped_fields.append("capabilities")
    loss.dropped_fields.append("compliance")
    if uap_agent.ui is not None:
        loss.dropped_fields.append("ui")
    if uap_agent.tags:
        loss.dropped_fields.append("tags")
    if tool_urn_refs:
        loss.coerced_fields.append("tools")
        loss.notes.append(
            "URN-only tool references cannot be embedded in OpenAI tools array; "
            "preserved under metadata.uap_tool_refs."
        )
    return assistant, loss


def to_openai(obj: Union[Tool, Agent]) -> Tuple[Dict[str, Any], LossInfo]:
    """Dispatch to the right encoder by Python type.

    ``Tool``  -> OpenAI function-tool dict
    ``Agent`` -> OpenAI Assistants v2 dict
    """
    if isinstance(obj, Tool):
        return tool_to_openai_function(obj)
    if isinstance(obj, Agent):
        return agent_to_openai_assistant(obj)
    raise TypeError(
        f"to_openai expects Tool or Agent; got {type(obj).__name__}"
    )
