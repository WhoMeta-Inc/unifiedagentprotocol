from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from unifiedagentprotocol.runtime import AgentTaskPayload, TaskEnvelope


def _envelope(**changes):
    values = {
        "id": "urn:uap:task:task-1",
        "connection_id": UUID("11111111-1111-1111-1111-111111111111"),
        "produced_by": "urn:uap:agent:producer",
        "tenant_id": "partner-tenant",
        "nonce": "nonce-1",
        "expires_at": datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc),
        "payload": AgentTaskPayload(
            target_agent="urn:uap:agent:target",
            title="Review facts",
            description="Bounded input",
            correlation_id="corr-1",
        ),
        "signature": "ed25519:" + "A" * 86 + "==",
    }
    values.update(changes)
    return TaskEnvelope(**values)


def test_task_envelope_has_stable_cross_language_statement():
    statement = _envelope().canonical_statement()
    lines = statement.splitlines()
    assert len(lines) == 12
    assert lines[7] == "1783944000"
    assert lines[0] == "MS4w"


def test_task_envelope_rejects_unknown_fields_and_non_uap_identity():
    with pytest.raises(ValidationError):
        _envelope(id="plain-id")
    with pytest.raises(ValidationError):
        _envelope(untrusted_tenant_override="tenant-b")
