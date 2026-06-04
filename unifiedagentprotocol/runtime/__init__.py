# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP runtime — optional FastAPI adapter.

Importing from this package requires the ``[runtime]`` extra:

    pip install unified-agent-protocol[runtime]
"""
from .server import create_app

__all__ = ["create_app"]
