# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Bidirectional bridge between UAP 1.0 and Swagger v2.0.

Swagger 2.0 predates OpenAPI 3 and differs in several important ways:

* ``host``, ``basePath``, ``schemes`` instead of ``servers``,
* ``parameters[in=body]`` carries the request body schema,
* ``definitions`` instead of ``components.schemas``,
* ``securityDefinitions`` instead of ``components.securitySchemes``.

The bridge maps these constructs to/from UAP while recording lossy
conversions (notably mTLS / AWS SigV4 / OAuth2 nuances).

Public entry-points:

    to_swagger(obj)        -> (spec: dict, LossInfo)
    from_swagger(spec)     -> (Agent, LossInfo)
"""
from __future__ import annotations

from .to_swagger import agent_to_swagger, to_swagger
from .from_swagger import agent_from_swagger, from_swagger

__all__ = [
    "to_swagger",
    "from_swagger",
    "agent_to_swagger",
    "agent_from_swagger",
]
