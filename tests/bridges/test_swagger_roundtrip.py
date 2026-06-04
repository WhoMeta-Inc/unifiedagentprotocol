# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Smoke / shape tests for the UAP <-> Swagger 2.0 bridge."""
from __future__ import annotations

import pytest

from unifiedagentprotocol.bridges.swagger import from_swagger, to_swagger
from unifiedagentprotocol.core import (
    Agent,
    AuthConfig,
    AuthType,
    Endpoint,
    Parameter,
    ParameterLocation,
    ParameterSchema,
    Tool,
    Transport,
)


def test_v2_parse_smoke() -> None:
    """A minimal Swagger 2.0 spec parses into an Agent with at least one Tool."""
    spec = {
        "swagger": "2.0",
        "info": {
            "title": "Petstore (Swagger Minimal)",
            "version": "1.0.0",
            "description": "Example Swagger document for UAP demo",
        },
        "host": "petstore.example",
        "basePath": "/v1",
        "schemes": ["https"],
        "paths": {
            "/pets": {
                "get": {
                    "summary": "List pets",
                    "description": "Returns all pets",
                    "operationId": "listPets",
                    "responses": {
                        "200": {
                            "description": "An array of pets",
                            "schema": {
                                "type": "array",
                                "items": {"$ref": "#/definitions/Pet"},
                            },
                        }
                    },
                }
            },
            "/pets/{id}": {
                "post": {
                    "summary": "Add a pet",
                    "description": "Create a new pet",
                    "operationId": "addPet",
                    "parameters": [
                        {"name": "id", "in": "path", "required": True, "type": "string"},
                        {
                            "name": "body",
                            "in": "body",
                            "required": True,
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "tag": {"type": "string"},
                                },
                                "required": ["name"],
                            },
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "Created",
                            "schema": {"type": "object"},
                        }
                    },
                }
            },
        },
    }
    agent, loss = from_swagger(spec)
    assert isinstance(agent, Agent)
    assert agent.id.startswith("urn:uap:agent:")
    # At least one tool, with the operationId-derived name.
    assert len(agent.tools) >= 1
    names = {t.name for t in agent.tools if isinstance(t, Tool)}
    assert "listPets" in names
    assert "addPet" in names
    # Endpoint synthesized from host+basePath.
    assert agent.endpoints
    assert agent.endpoints[0].url == "https://petstore.example/v1"

    # to_swagger should produce a v2 doc as well.
    rebuilt, _ = to_swagger(agent)
    assert rebuilt["swagger"] == "2.0"
    assert "paths" in rebuilt
    # The recovered tool with path params should expose them.
    add_pet_tool = next(t for t in agent.tools if isinstance(t, Tool) and t.name == "addPet")
    locs = {p.name: p.location for p in add_pet_tool.parameters}
    assert locs["id"] is ParameterLocation.PATH
    assert "name" in locs
    assert locs["name"] is ParameterLocation.BODY


def test_rejects_v3() -> None:
    """``from_swagger`` rejects an OpenAPI 3.x document."""
    with pytest.raises(ValueError):
        from_swagger({"openapi": "3.0.3"})


def test_to_swagger_records_mtls_downgrade() -> None:
    """Exporting an mTLS agent records a coercion in LossInfo."""
    body_p = Parameter(
        name="payload",
        schema=ParameterSchema(type="string"),
        required=True,
        location=ParameterLocation.BODY,
    )
    tool = Tool(
        id="urn:uap:tool:secret-payload",
        name="secret_payload",
        description="Send a secret payload.",
        parameters=[body_p],
    )
    agent = Agent(
        id="urn:uap:agent:secure",
        name="secure",
        description="A secure agent.",
        tools=[tool],
        endpoints=[Endpoint(transport=Transport.HTTP, url="https://api.example.com/secure")],
        auth=AuthConfig(type=AuthType.MTLS, secret_ref="vault://kv/data/secure#cert"),
    )
    spec, loss = to_swagger(agent)
    assert spec["swagger"] == "2.0"
    assert "auth.type" in loss.coerced_fields
    assert any("mtls" in n.lower() for n in loss.notes)
