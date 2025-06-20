"""Example LangChain Tool definition for UAP examples."""
from langchain.tools import Tool

def hello(name: str) -> str:
    """Return a greeting for the given name."""
    return f"Hello {name}!"

# Exported tool instance
greet_tool = Tool.from_function(
    func=hello,
    name="hello_tool",
    description="Greets a user by name.",
)
