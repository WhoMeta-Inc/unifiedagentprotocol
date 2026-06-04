# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""OpenAI tool / Assistants v2 -> UAP conversion.

Inverse of :mod:`to_openai`. Bare and wrapped function-tool dicts are both
accepted. When no UAP URN is smuggled through ``metadata.uap_urn`` we
synthesize one deterministically from the ``name`` field.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple, Union

from unifiedagentprotocol.core import (
    Agent,
    LossInfo,
    Parameter,
    ParameterSchema,
    Skill,
    Tool,
)


# ---------------------------------------------------------------------------
# URN helpers
# ---------------------------------------------------------------------------

_SLUG_BAD = re.compile(r"[^a-z0-9._-]+")


def _slugify(name: str) -> str:
    s = name.strip().lower().replace(" ", "-")
    s = _SLUG_BAD.sub("-", s)
    s = s.strip("-._")
    if not s or not (s[0].isalnum()):
        s = f"x-{s}" if s else "unnamed"
    return s


def _synthesize_urn(kind: str, name: str) -> str:
    return f"urn:uap:{kind}:{_slugify(name)}"


# ---------------------------------------------------------------------------
# JSON Schema -> Parameter list
# ---------------------------------------------------------------------------

_PARAM_SCHEMA_FIELDS = {
    "type",
    "description",
    "format",
    "enum",
    "default",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "items",
    "properties",
    "required",
    "oneOf",
    "anyOf",
    "allOf",
    "$ref",
}


def _schema_dict_to_parameter_schema(schema: Dict[str, Any]) -> ParameterSchema:
    """Build a ParameterSchema from a JSON-Schema-style dict.

    Unknown keys (besides ``x-*`` extensions) are preserved on the model
    via ``extra="allow"``.
    """
    # Only forward keys ParameterSchema understands plus extensions;
    # other keys are passed through and stored as extras.
    return ParameterSchema.model_validate(schema)


def _json_schema_to_parameters(
    schema: Dict[str, Any],
    loss: LossInfo,
) -> List[Parameter]:
    """Split an ``object`` JSON schema into a UAP Parameter list."""
    if not isinstance(schema, dict):
        return []
    if schema.get("type") not in (None, "object"):
        loss.coerced_fields.append("parameters")
        loss.notes.append(
            f"Top-level parameters schema has type={schema.get('type')!r}; "
            "wrapped as a single 'input' parameter."
        )
        single = Parameter(
            name="input",
            schema=_schema_dict_to_parameter_schema(schema),
            required=True,
        )
        return [single]

    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    params: List[Parameter] = []
    for name, sub in props.items():
        if not isinstance(sub, dict):
            continue
        params.append(
            Parameter(
                name=name,
                schema=_schema_dict_to_parameter_schema(sub),
                required=name in required,
            )
        )
    return params


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

def _unwrap_function(fn: Dict[str, Any]) -> Dict[str, Any]:
    """Return the inner ``function`` body whether it is wrapped or bare."""
    if (
        isinstance(fn, dict)
        and fn.get("type") == "function"
        and isinstance(fn.get("function"), dict)
    ):
        return fn["function"]
    return fn


def tool_from_openai_function(fn: Dict[str, Any]) -> Tuple[Tool, LossInfo]:
    """Convert an OpenAI function tool (wrapped or bare) into a UAP Tool."""
    if not isinstance(fn, dict):
        raise TypeError("tool_from_openai_function expects a dict.")

    body = _unwrap_function(fn)
    loss = LossInfo()

    name = body.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("OpenAI function tool is missing a 'name'.")
    description = body.get("description") or ""

    parameters_schema = body.get("parameters") or {}
    if not isinstance(parameters_schema, dict):
        loss.coerced_fields.append("parameters")
        parameters_schema = {}
    parameters = _json_schema_to_parameters(parameters_schema, loss)

    # Recover identity from smuggled metadata if present, else synthesize.
    md = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    urn = md.get("uap_urn") if isinstance(md, dict) else None
    if not isinstance(urn, str) or not urn.startswith("urn:uap:tool:"):
        urn = _synthesize_urn("tool", name)
        loss.notes.append(
            "OpenAI payload carried no uap_urn; tool URN was synthesized from name."
        )
    version = md.get("uap_version") if isinstance(md, dict) else None
    display_name = md.get("uap_display_name") if isinstance(md, dict) else None

    tool_kwargs: Dict[str, Any] = {
        "id": urn,
        "name": name,
        "description": description,
        "parameters": parameters,
    }
    if isinstance(version, str) and version:
        tool_kwargs["version"] = version
    if isinstance(display_name, str) and display_name:
        tool_kwargs["display_name"] = display_name

    if body.get("strict") is not None:
        # OpenAI's strict-mode flag has no UAP analogue.
        loss.dropped_fields.append("function.strict")

    return Tool(**tool_kwargs), loss


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------

def agent_from_openai_assistant(a: Dict[str, Any]) -> Tuple[Agent, LossInfo]:
    """Convert an OpenAI Assistants v2 body into a UAP Agent."""
    if not isinstance(a, dict):
        raise TypeError("agent_from_openai_assistant expects a dict.")

    loss = LossInfo()
    name = a.get("name") or "assistant"
    description = a.get("description") or a.get("instructions") or ""
    instructions = a.get("instructions")
    model = a.get("model")
    md_in = a.get("metadata") if isinstance(a.get("metadata"), dict) else {}
    md_in = dict(md_in or {})

    urn = md_in.pop("uap_urn", None)
    if not isinstance(urn, str) or not urn.startswith("urn:uap:agent:"):
        urn = _synthesize_urn("agent", name)
        loss.notes.append(
            "OpenAI assistant carried no uap_urn; agent URN was synthesized from name."
        )
    version = md_in.pop("uap_version", None)
    display_name = md_in.pop("uap_display_name", None)
    tool_refs = md_in.pop("uap_tool_refs", None)

    # Parse tools list. Function tools become UAP Tools; non-function entries
    # (code_interpreter, file_search, etc.) cannot be expressed in UAP and
    # are recorded as losses.
    tools_out: List[Any] = []
    for idx, t in enumerate(a.get("tools") or []):
        if not isinstance(t, dict):
            continue
        ttype = t.get("type", "function")
        if ttype == "function":
            tool_obj, t_loss = tool_from_openai_function(t)
            tools_out.append(tool_obj)
            for f in t_loss.dropped_fields:
                loss.dropped_fields.append(f"tools[{idx}].{f}")
            for f in t_loss.coerced_fields:
                loss.coerced_fields.append(f"tools[{idx}].{f}")
            loss.notes.extend(t_loss.notes)
        else:
            loss.dropped_fields.append(f"tools[{idx}]")
            loss.notes.append(
                f"OpenAI built-in tool type {ttype!r} has no UAP analogue; dropped."
            )

    # URN-only references smuggled through metadata are restored as strings.
    if isinstance(tool_refs, list):
        for ref in tool_refs:
            if isinstance(ref, str):
                tools_out.append(ref)

    # Build the round-tripped metadata. Anything not recognized as a UAP
    # smuggling key is preserved verbatim, and OpenAI-specific knobs (model,
    # instructions) are stashed for the reverse trip.
    metadata: Dict[str, Any] = {}
    if model:
        metadata["openai_model"] = model
    if instructions:
        metadata["openai_instructions"] = instructions
    for k, v in md_in.items():
        metadata[k] = v

    agent_kwargs: Dict[str, Any] = {
        "id": urn,
        "name": name,
        "description": description,
        "tools": tools_out,
        "metadata": metadata,
    }
    if isinstance(version, str) and version:
        agent_kwargs["version"] = version
    if isinstance(display_name, str) and display_name:
        agent_kwargs["display_name"] = display_name

    return Agent(**agent_kwargs), loss


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def from_openai(obj: Dict[str, Any]) -> Tuple[Union[Tool, Agent], LossInfo]:
    """Autodetect whether ``obj`` is an OpenAI function tool or Assistant.

    Detection rules:

    * If ``obj`` has ``type == "function"`` or a ``parameters`` field with
      no ``model`` / ``instructions`` / ``tools`` list, treat as a Tool.
    * Otherwise treat as an Assistant body (Agent).
    """
    if not isinstance(obj, dict):
        raise TypeError("from_openai expects a dict.")

    is_wrapped_tool = obj.get("type") == "function" and isinstance(
        obj.get("function"), dict
    )
    looks_like_assistant = (
        "model" in obj
        or "instructions" in obj
        or (isinstance(obj.get("tools"), list) and "name" in obj)
    )
    if is_wrapped_tool and not looks_like_assistant:
        return tool_from_openai_function(obj)
    if looks_like_assistant:
        return agent_from_openai_assistant(obj)
    # Bare tool form: {"name": ..., "parameters": {...}}.
    if "name" in obj and ("parameters" in obj or "description" in obj):
        return tool_from_openai_function(obj)
    raise ValueError(
        "from_openai could not classify the payload as a function tool or "
        "an Assistant body."
    )
