# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and Google Gemini function declarations.

Gemini exposes callable tools as ``FunctionDeclaration`` objects with
``name``, ``description``, and an OpenAPI-3.0 style ``parameters`` schema.
The OpenAPI schema's ``type`` field uses uppercase enum-style values
(``STRING``, ``INTEGER``, ``NUMBER``, ``BOOLEAN``, ``ARRAY``, ``OBJECT``);
this bridge emits and consumes that convention.

Gemini's ``ToolConfig`` (which groups function declarations and selects an
invocation ``mode`` of ``AUTO``/``ANY``/``NONE``) is out of scope here —
this bridge produces and consumes individual ``FunctionDeclaration`` dicts.

The two public entry-points are::

    to_gemini(obj)            -> (function_decl_dict: dict, LossInfo)
    from_gemini(decl_dict)    -> (Tool, LossInfo)
"""
from __future__ import annotations

from .to_gemini import to_gemini, tool_to_gemini
from .from_gemini import from_gemini, tool_from_gemini

__all__ = [
    "to_gemini",
    "from_gemini",
    "tool_to_gemini",
    "tool_from_gemini",
]
