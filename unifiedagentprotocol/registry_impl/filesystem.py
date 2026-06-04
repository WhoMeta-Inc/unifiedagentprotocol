# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Filesystem-backed implementation of the :class:`Registry` protocol.

Each record is persisted as a single JSON envelope file at::

    {root}/{kind}/{slug}.json

where ``{kind}`` is ``agent | tool | manifest`` and ``{slug}`` is the
URN slug (the part after the third colon). Writes are atomic — a
temporary file is written next to the destination and then renamed,
so concurrent readers never observe a half-written record.

This backend is intentionally simple: there is no index, no caching,
and no in-memory mirror. Each call walks the relevant directory. That
is fine for the development workflows the runtime targets; production
deployments should swap in a database-backed implementation.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional

from unifiedagentprotocol.core import Agent, Envelope, Kind, Manifest, Tool

from .base import RegistryObject


_KIND_FOR_TYPE = {
    Tool: Kind.TOOL,
    Agent: Kind.AGENT,
    Manifest: Kind.MANIFEST,
}


_KIND_TO_TYPE = {
    Kind.TOOL: Tool,
    Kind.AGENT: Agent,
    Kind.MANIFEST: Manifest,
}


def _kind_of(obj: RegistryObject) -> Kind:
    for typ, kind in _KIND_FOR_TYPE.items():
        if isinstance(obj, typ):
            return kind
    raise TypeError(
        f"FilesystemRegistry cannot store object of type {type(obj).__name__}"
    )


def _slug_from_urn(urn: str) -> str:
    """Extract the trailing slug component of a UAP URN.

    The URN format is ``urn:uap:<kind>:<slug>`` — we want the final
    component. We tolerate a trailing colon-less identifier so that
    objects round-tripped from foreign systems still have a stable
    on-disk filename.
    """
    parts = urn.split(":")
    if len(parts) < 4:
        raise ValueError(f"Cannot derive slug from URN: {urn!r}")
    return parts[-1]


def _haystacks(obj: RegistryObject) -> List[str]:
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


class FilesystemRegistry:
    """JSON-on-disk implementation of the :class:`Registry` protocol.

    Records are persisted as one envelope per file under ``root/<kind>/``.
    A re-entrant lock serialises filesystem mutations to keep behaviour
    deterministic when multiple threads share a single instance — the
    backend remains process-local; multi-process coordination is out of
    scope for this reference implementation.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._lock = threading.RLock()
        # Make sure the per-kind subdirectories exist so writes never
        # race on directory creation.
        for kind in Kind:
            (self._root / kind.value).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path_for(self, kind: Kind, slug: str) -> Path:
        return self._root / kind.value / f"{slug}.json"

    def _path_for_urn(self, urn: str, kind: Optional[Kind] = None) -> Path:
        slug = _slug_from_urn(urn)
        if kind is None:
            parts = urn.split(":")
            try:
                kind = Kind(parts[2])
            except (IndexError, ValueError) as exc:
                raise ValueError(f"Cannot derive kind from URN: {urn!r}") from exc
        return self._path_for(kind, slug)

    def _write_envelope(self, path: Path, payload: Dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp-file in the same directory + rename.
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            # Best-effort cleanup; ignore secondary errors so the
            # original exception surfaces.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    def _load_envelope(self, path: Path) -> Optional[RegistryObject]:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return None
        except json.JSONDecodeError:
            # Refuse to silently lose a malformed file — surface the
            # error to the caller.
            raise
        # Dispatch on the envelope's declared kind so we avoid any
        # ambiguity in pydantic's Union resolution for ``payload``.
        kind_value = data.get("kind") if isinstance(data, dict) else None
        if kind_value is None:
            envelope = Envelope.model_validate(data)
            return envelope.payload  # type: ignore[return-value]
        try:
            kind = Kind(kind_value)
        except ValueError as exc:
            raise ValueError(
                f"Unknown envelope kind {kind_value!r} in {path}"
            ) from exc
        payload_type = _KIND_TO_TYPE[kind]
        payload_data = data.get("payload", {})
        payload = payload_type.model_validate(payload_data)
        return payload

    def _iter_all(self) -> List[RegistryObject]:
        out: List[RegistryObject] = []
        for kind in Kind:
            kind_dir = self._root / kind.value
            if not kind_dir.is_dir():
                continue
            # Sort to make iteration deterministic across filesystems
            # and platforms; insertion order has no meaning on disk.
            for path in sorted(kind_dir.glob("*.json")):
                obj = self._load_envelope(path)
                if obj is not None:
                    out.append(obj)
        return out

    # ------------------------------------------------------------------
    # Registry protocol
    # ------------------------------------------------------------------

    def register(self, obj: RegistryObject) -> None:
        kind = _kind_of(obj)
        path = self._path_for(kind, _slug_from_urn(obj.id))
        envelope = Envelope.of(obj)
        payload = envelope.model_dump(mode="json", exclude_none=True, by_alias=True)
        with self._lock:
            self._write_envelope(path, payload)

    def get(self, urn: str) -> Optional[RegistryObject]:
        try:
            path = self._path_for_urn(urn)
        except ValueError:
            return None
        with self._lock:
            return self._load_envelope(path)

    def list(
        self,
        kind: Optional[Kind] = None,
        tag: Optional[str] = None,
    ) -> List[RegistryObject]:
        with self._lock:
            results: List[RegistryObject] = []
            if kind is not None:
                kinds = [kind]
            else:
                kinds = list(Kind)
            for k in kinds:
                kind_dir = self._root / k.value
                if not kind_dir.is_dir():
                    continue
                for path in sorted(kind_dir.glob("*.json")):
                    obj = self._load_envelope(path)
                    if obj is None:
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
            candidates = (
                self.list(kind=kind) if kind is not None else self._iter_all()
            )
            for obj in candidates:
                for hay in _haystacks(obj):
                    if needle in hay.lower():
                        results.append(obj)
                        break
                if len(results) >= limit:
                    break
            return results

    def delete(self, urn: str) -> bool:
        try:
            path = self._path_for_urn(urn)
        except ValueError:
            return False
        with self._lock:
            try:
                path.unlink()
            except FileNotFoundError:
                return False
            return True


__all__ = ["FilesystemRegistry"]
