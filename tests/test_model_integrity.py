"""Model integrity tests – ensure round-trip serialisation and validation."""
import pytest

from unifiedagentprotocol.models.agent import Agent
from unifiedagentprotocol.models.tool import Tool, ToolParam, OutputSchema
from unifiedagentprotocol.models.common import Trigger


def sample_tool() -> Tool:  # helper
    return Tool(
        name="echo",
        description="Return the same text",
        parameters=[ToolParam(name="text", type="string", required=True)],
        output=OutputSchema(schema={"type": "object", "properties": {"text": {"type": "string"}}}),
        triggers=[Trigger(type="manual")],
    )


def test_tool_round_trip():
    tool = sample_tool()
    data = tool.dict()
    clone = Tool(**data)
    assert clone == tool


def test_agent_round_trip():
    tool = sample_tool()
    agent = Agent(name="EchoBot", description="Simple echo bot", tools=[tool])
    data = agent.dict()
    clone = Agent(**data)
    assert clone == agent


def test_tool_validation_missing_param():
    with pytest.raises(Exception):
        # name is required
        Tool(description="Invalid", parameters=[])
