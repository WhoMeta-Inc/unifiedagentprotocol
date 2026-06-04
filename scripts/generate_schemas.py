#!/usr/bin/env python3
# Copyright 2025-2026 WhoMeta Inc.
# Licensed under the Apache License, Version 2.0
"""Generate canonical JSON Schemas for UAP 1.0 from the Pydantic models.

Writes to ``schemas/uap/1.0/``. Run from the repo root:

    python scripts/generate_schemas.py
"""
from __future__ import annotations

import json
from pathlib import Path

from unifiedagentprotocol import Agent, Envelope, Manifest, Tool


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "schemas" / "uap" / "1.0"
    out.mkdir(parents=True, exist_ok=True)

    targets = {
        "envelope.schema.json": Envelope,
        "agent.schema.json": Agent,
        "tool.schema.json": Tool,
        "manifest.schema.json": Manifest,
    }
    for filename, model in targets.items():
        schema = model.model_json_schema(by_alias=True)
        schema["$id"] = f"https://schemas.whometa.io/uap/1.0/{filename}"
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (out / filename).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
        print(f"wrote {out / filename}")


if __name__ == "__main__":
    main()
