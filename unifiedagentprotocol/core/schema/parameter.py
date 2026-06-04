# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Parameter and ParameterSchema — strict JSON-Schema-typed inputs/outputs."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from ._base import UAPModel


class ParameterLocation(str, Enum):
    """Where the parameter is carried at the protocol level."""

    BODY = "body"
    QUERY = "query"
    PATH = "path"
    HEADER = "header"
    CONTEXT = "context"  # passed by the agent runtime, not by the caller


_ALLOWED_JSON_SCHEMA_TYPES = {
    "string",
    "integer",
    "number",
    "boolean",
    "object",
    "array",
    "null",
}


class ParameterSchema(UAPModel):
    """A constrained subset of JSON Schema Draft 2020-12.

    Custom UAP fields use the ``x-uap-*`` namespace and are preserved through
    round-trips.
    """

    type: Optional[str] = None
    description: Optional[str] = None
    format: Optional[str] = Field(
        None,
        description='JSON-Schema format hint (e.g. "email", "uri", "date-time").',
    )
    enum: Optional[List[Any]] = None
    default: Optional[Any] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    min_length: Optional[int] = Field(None, alias="minLength")
    max_length: Optional[int] = Field(None, alias="maxLength")
    pattern: Optional[str] = None
    items: Optional["ParameterSchema"] = None
    properties: Optional[Dict[str, "ParameterSchema"]] = None
    required: Optional[List[str]] = None
    one_of: Optional[List["ParameterSchema"]] = Field(None, alias="oneOf")
    any_of: Optional[List["ParameterSchema"]] = Field(None, alias="anyOf")
    all_of: Optional[List["ParameterSchema"]] = Field(None, alias="allOf")
    ref: Optional[str] = Field(None, alias="$ref")

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _ALLOWED_JSON_SCHEMA_TYPES:
            raise ValueError(
                f"Unsupported JSON Schema type '{v}'. Allowed: {sorted(_ALLOWED_JSON_SCHEMA_TYPES)}"
            )
        return v


ParameterSchema.model_rebuild()


class Parameter(UAPModel):
    """One named input or output value of a Tool."""

    name: str = Field(..., description="Identifier used in invocations.")
    schema_: ParameterSchema = Field(..., alias="schema")
    required: bool = True
    location: ParameterLocation = ParameterLocation.BODY
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_format(cls, v: str) -> str:
        if not v or not v[0].isalpha() and v[0] != "_":
            raise ValueError(
                "Parameter.name must start with a letter or underscore."
            )
        return v
