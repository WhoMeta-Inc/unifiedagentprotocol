# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Registry protocol — pluggable storage backend contract.

A *registry* is an object that stores UAP :class:`Tool`, :class:`Agent`,
and :class:`Manifest` records keyed by their URN identifier and lets
callers list / search / delete them. Concrete backends (in-memory,
filesystem, database, network) implement this :class:`typing.Protocol`
so they can be passed interchangeably to the runtime adapter.

The protocol is intentionally small and synchronous: backends that
fronts a remote service should perform their own I/O inside each method.
"""
from __future__ import annotations

from typing import List, Optional, Protocol, Union, runtime_checkable

from unifiedagentprotocol.core import Agent, Kind, Manifest, Tool


#: Anything that can live in a registry.
RegistryObject = Union[Tool, Agent, Manifest]


@runtime_checkable
class Registry(Protocol):
    """Pluggable storage backend for UAP records.

    All implementations MUST follow these semantics:

    * ``register`` overwrites an existing record with the same URN.
    * ``get`` returns ``None`` for unknown URNs (never raises).
    * ``list`` accepts optional ``kind`` and ``tag`` filters. When both
      are supplied the result is the intersection (logical AND). Tag
      filter is applied case-sensitively against the object's ``tags``
      attribute and to ``Skill.tags`` for agents.
    * ``search`` performs a **case-insensitive substring match** against
      the record's ``name``, ``display_name``, ``description`` and
      every entry in ``tags``. The search is OR across those fields:
      a record matches when *any* one of them contains the query
      substring. Results are capped at ``limit`` items, in insertion /
      backend-natural order. ``kind`` may further restrict the result
      set.
    * ``delete`` returns ``True`` when a record was removed, ``False``
      when no record matched.

    Implementations are not required to be thread-safe at the protocol
    level — concrete classes document their own concurrency contract.
    """

    def register(self, obj: RegistryObject) -> None:
        """Insert or overwrite a record. Idempotent on URN."""
        ...

    def get(self, urn: str) -> Optional[RegistryObject]:
        """Fetch a record by URN, or ``None`` if no such record exists."""
        ...

    def list(
        self,
        kind: Optional[Kind] = None,
        tag: Optional[str] = None,
    ) -> List[RegistryObject]:
        """List records, optionally filtered by kind and/or tag.

        ``kind`` filters by the UAP envelope kind. ``tag`` is checked
        against the object's ``tags`` list. When both are passed, only
        records matching both filters are returned.
        """
        ...

    def search(
        self,
        query: str,
        *,
        kind: Optional[Kind] = None,
        limit: int = 20,
    ) -> List[RegistryObject]:
        """Case-insensitive substring match.

        The query is matched against ``name``, ``display_name``,
        ``description`` and every entry in ``tags``. A record is
        returned when *any* of those fields contains ``query`` as a
        case-insensitive substring. The optional ``kind`` further
        restricts the result set. Up to ``limit`` records are returned
        in insertion order.
        """
        ...

    def delete(self, urn: str) -> bool:
        """Remove a record. Returns ``True`` if a record was removed."""
        ...


__all__ = ["Registry", "RegistryObject"]
