# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP registry — pluggable storage backends for Tools, Agents, Manifests.

The ``registry_impl`` package (named to avoid colliding with the
``registry`` attribute names in user code) provides reference
implementations of the ``Registry`` protocol.
"""
from .base import Registry
from .memory import InMemoryRegistry
from .filesystem import FilesystemRegistry

__all__ = ["Registry", "InMemoryRegistry", "FilesystemRegistry"]
