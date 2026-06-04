# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""UAP bridges — bidirectional adapters to foreign agent/tool formats.

Every bridge ships two callables:

    def to_<format>(uap_obj) -> tuple[ForeignObj, LossInfo]
    def from_<format>(foreign_obj) -> tuple[UAPObj, LossInfo]

Bridges may only depend on ``unifiedagentprotocol.core`` and the standard
library (plus optional format-specific deps installed via extras).
"""
