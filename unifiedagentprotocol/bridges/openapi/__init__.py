# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and OpenAPI v3.

OpenAPI v3 is a *path-oriented* specification: a document maps URL paths to
HTTP operations, where each operation declares parameters (path, query,
header) and a request body. UAP, by contrast, is *tool-oriented*: every
:class:`Tool` is an executable function with named :class:`Parameter`
inputs and a single output schema.

The bridge canonicalises this mismatch by:

* one Tool  -> one ``POST /tools/{name}`` path,
* parameters with ``location in {path, query, header}`` becoming OpenAPI
  ``parameters`` entries,
* parameters with ``location=body`` merged into a single
  ``requestBody.content.application/json.schema``,
* the UAP enterprise envelope (capabilities, compliance, auth, cost,
  triggers, ui) surfaced via ``x-uap-*`` extensions on the operation.

The two public entry-points are:

    to_openapi(obj)        -> (spec: dict, LossInfo)
    from_openapi(spec)     -> (Agent, LossInfo)
"""
from __future__ import annotations

from .to_openapi import agent_to_openapi, to_openapi, tool_to_openapi
from .from_openapi import agent_from_openapi, from_openapi

__all__ = [
    "to_openapi",
    "from_openapi",
    "agent_to_openapi",
    "agent_from_openapi",
    "tool_to_openapi",
]
