from mcp.server import MCPServer

mcp = MCPServer("day44-hello")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two whole numbers and return the sum."""
    return a + b


@mcp.tool()
def count_words(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())


@mcp.resource("info://server")
def server_info() -> str:
    """What this practice server is for."""
    return "Day 44 practice server: two tools, one resource, one resource template."


@mcp.resource("greeting://{name}")
def greeting(name: str) -> str:
    """A greeting for the given name."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    mcp.run()