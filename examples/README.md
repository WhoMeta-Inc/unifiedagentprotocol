# UAP Examples

Quick-start inputs for trying out the Unified Agent Protocol SDK.

| File | Purpose |
|------|---------|
| `openwebui/openwebui_tool.json` | Minimal OpenWebUI tool definition to test `parse_openwebui` and CLI conversion. |
| `langchain/langchain_tool.py` | LangChain `Tool` instance that can be imported and fed to `parse_langchain`. |
| `openapi/petstore.yaml` | Tiny OpenAPI 3 spec for `parse_openapi`. |
| `agent/agent_minimal.json` | Hand-crafted UAP Agent used to demo the export helpers (`to_mcp`, `to_a2a`, `to_openapi`). |

## CLI demo

```bash
# Convert OpenWebUI tool → MCP
uap --input examples/openwebui/openwebui_tool.json --format mcp > examples/out/openwebui_mcp.json

# Convert Agent → A2A
python - <<'PY'
from pathlib import Path, PurePath
import json
from unifiedagentprotocol.models.agent import Agent
from unifiedagentprotocol.export.to_a2a import agent_to_a2a
agent = Agent.model_validate_json(Path('examples/agent/agent_minimal.json').read_text())
print(json.dumps(agent_to_a2a(agent), indent=2))
PY
```

Feel free to extend or replace these samples.
