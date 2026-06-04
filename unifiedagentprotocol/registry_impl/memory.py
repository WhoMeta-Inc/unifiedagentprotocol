# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""In-memory implementation of the :class:`Registry` protocol.

Suitable for tests, single-process embeddings, and as a reference
implementation. Records are kept in a plain ``dict`` keyed by URN; all
mutating and reading methods acquire a re-entrant lock so the registry
can be shared between threads.
"""
from __future__ import annotations

import threading
from typing import Dict, List, Optional

from unifiedagentprotocol.core import Agent, Kind, Manifest, Tool

from .base import RegistryObject


_KIND_FOR_TYPE = {
    Tool: Kind.TOOL,
    Agent: Kind.AGENT,
    Manifest: Kind.MANIFEST,
}


def _kind_of(obj: RegistryObject) -> Kind:
    for typ, kind in _KIND_FOR_TYPE.items():
        if isinstance(obj, typ):
            return kind
    raise TypeError(
        f"InMemoryRegistry cannot store object of type {type(obj).__name__}"
    )


def _haystacks(obj: RegistryObject) -> List[str]:
    """Return the strings considered by ``search`` for one record."""
    fields: List[str] = []
    name = getattr(obj, "name", None)
    if isinstance(name, str):
        fields.append(name)
    display_name = getattr(obj, "display_name", None)
    if isinstance(display_name, str):
        fields.append(display_name)
    description = getattr(obj, "description", None)
    if isinstance(description, str):
        fields.append(description)
    tags = getattr(obj, "tags", None) or []
    for tag in tags:
        if isinstance(tag, str):
            fields.append(tag)
    return fields


class InMemoryRegistry:
    """Thread-safe in-memory registry.

    Records are stored in a plain ``dict[str, RegistryObject]`` keyed by
    URN. A :class:`threading.RLock` guards every public method so the
    same instance may be shared across threads (including re-entrant
    callers).

    Iteration order matches insertion order, which is what callers of
    :meth:`list` and :meth:`search` typically expect.
    """

    def __init__(self) -> None:
        self._records: Dict[str, RegistryObject] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registry protocol
    # ------------------------------------------------------------------

    def register(self, obj: RegistryObject) -> None:
        # Validate the object's type up-front so callers get an immediate
        # error rather than a silent storage of an unknown kind.
        _kind_of(obj)
        with self._lock:
            self._records[obj.id] = obj

    def get(self, urn: str) -> Optional[RegistryObject]:
        with self._lock:
            return self._records.get(urn)

    def list(
        self,
        kind: Optional[Kind] = None,
        tag: Optional[str] = None,
    ) -> List[RegistryObject]:
        with self._lock:
            results: List[RegistryObject] = []
            for obj in self._records.values():
                if kind is not None and _kind_of(obj) is not kind:
                    continue
                if tag is not None:
                    tags = getattr(obj, "tags", None) or []
                    if tag not in tags:
                        continue
                results.append(obj)
            return results

    def search(
        self,
        query: str,
        *,
        kind: Optional[Kind] = None,
        limit: int = 20,
    ) -> List[RegistryObject]:
        if limit <= 0:
            return []
        needle = query.lower()
        with self._lock:
            results: List[RegistryObject] = []
            for obj in self._records.values():
                if kind is not None and _kind_of(obj) is not kind:
                    continue
                for hay in _haystacks(obj):
                    if needle in hay.lower():
                        results.append(obj)
                        break
                if len(results) >= limit:
                    break
            return results

    def delete(self, urn: str) -> bool:
        with self._lock:
            return self._records.pop(urn, None) is not None

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def __len__(self) -> int:  # pragma: no cover - trivial
        with self._lock:
            return len(self._records)

    def __contains__(self, urn: object) -> bool:  # pragma: no cover - trivial
        if not isinstance(urn, str):
            return False
        with self._lock:
            return urn in self._records


__all__ = ["InMemoryRegistry"]
