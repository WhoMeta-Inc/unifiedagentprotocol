# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP version constants.

`UAP_VERSION` is the wire-format version (semantic, ``major.minor``).
`SDK_VERSION` is the implementation version (semver of this package).

A bridge MAY reject payloads whose ``uap_version`` differs in the major
component. Minor bumps MUST be backwards compatible.
"""
from __future__ import annotations

UAP_VERSION: str = "1.0"
SDK_VERSION: str = "1.1.0"


def is_compatible(payload_version: str) -> bool:
    """Return True if ``payload_version`` is compatible with this SDK."""
    try:
        major, _minor = payload_version.split(".", 1)
    except ValueError:
        return False
    return major == UAP_VERSION.split(".", 1)[0]
