# Day 44 - MCP fundamentals (Week 9, Model Context Protocol)

## What MCP is
MCP (Model Context Protocol) is an open standard for connecting LLM apps to external tools and data.
A tool is written once as an MCP server; any MCP-capable app (Claude Desktop, Claude Code, Cursor, n8n,
your own LangGraph agent) can discover it and call it. No per-app glue code.

## What it actually does
1. Discovery: the app asks the server "what can you do?" (`tools/list`) and gets names, descriptions and input schemas.
2. The app hands those tools to the model as ordinary function definitions.
3. When the model asks for a tool, the app's client sends `tools/call` to the right server.
4. The server runs real code and returns the result; the model only reads and explains it.
The model never speaks MCP itself. MCP is the plumbing between the app and the tools.

Problem it solves: N apps x M tools = N*M integrations. With MCP it is N + M (each app builds a client once,
each tool is a server once). Analogy: USB-C instead of a different cable per device pair.

## Vocabulary
- Host: the app the user talks to (Claude Desktop). Owns the model and decides what it sees.
- Client: connector inside the host, one per server connection.
- Server: program that offers capabilities (my `server.py`).
- JSON-RPC 2.0: message format. Request = `method`, `params`, `id`; reply = same `id` + `result` or `error`.
- Transport: how messages travel. stdio = host starts the server as a child process and talks over stdin/stdout
  (local only). Streamable HTTP = server at a URL (remote, Day 46). HTTP+SSE = old remote transport, deprecated.
- Primitives (differ by who controls them):
  | Primitive | Controlled by | What | FreightLens example |
  |---|---|---|---|
  | Tool | model | action the model decides to call | check_invoice_against_quote |
  | Resource | app | read-only data loaded into context | document by id |
  | Prompt | user | template the user picks (like a slash command) | "explain this discrepancy" |
- Resource template: resource address with a gap, e.g. `greeting://{name}`. Listed by `resources/templates/list`,
  not `resources/list`. The client fills the gap and calls `resources/read` with `greeting://Mark`.
- Completion (`completion/complete`): optional autocomplete for prompt/template arguments. Not implemented here.
- Error -32601 "Method not found": standard JSON-RPC code; the server does not handle that method.
- MCPB (MCP Bundle, .mcpb / .dxt): a packaged local MCP server you drag into Claude Desktop Extensions to install.
- EPIPE ("broken pipe"): writing to a process's stdin after that process already exited.

## MCP vs function calling
Function calling = the model's ability to output "call X with these args".
MCP = how the app finds out what X is and runs it when X lives in a separate program.
"Function calling is how the model asks; MCP is how the app finds and runs what it asked for."

## Spec version (2026-07-28)
- Stateless core: no `initialize` handshake, no session id; every request carries its own version/client info
  in `_meta`, so any server instance can answer (easy load balancing, serverless). Matters on Day 46.
- Every result has `resultType` ("complete" / "input_required").
- Deprecated: Roots, Sampling, Logging, HTTP+SSE transport. Inspector v0.15.0 still shows Sampling/Roots tabs.
- Claude Desktop still sends the old `initialize` (log: "Era probe verdict: legacy"); the v2 server accepts it
  (backward compatibility).
- Python SDK v2: `from mcp.server import MCPServer`. Old tutorials use `FastMCP` (v1, import path removed).

## Code: mcp-server/day-44/server.py
```python
from mcp.server import MCPServer

mcp = MCPServer("day44-hello")            # name shown by hosts

@mcp.tool()                               # registers a tool
def add(a: int, b: int) -> int:           # type hints -> inputSchema
    """Add two whole numbers and return the sum."""   # docstring -> description the model reads
    return a + b

@mcp.tool()
def count_words(text: str) -> int:
    """Count the words in a piece of text."""
    return len(text.split())

@mcp.resource("info://server")            # fixed resource -> appears in resources/list
def server_info() -> str:
    """What this practice server is for."""
    return "Day 44 practice server: two tools, one resource, one resource template."

@mcp.resource("greeting://{name}")        # resource template -> resources/templates/list
def greeting(name: str) -> str:
    """A greeting for the given name."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()                             # stdio by default
```
- `python server.py` prints nothing and waits: a stdio server waits for a host to speak first. Correct.
- A tool returning a plain `int` comes back as `structuredContent: {"result": 2}` (structured content must be an object).

## Tools used
- MCP Inspector: `npx @modelcontextprotocol/inspector "<venv python>" "$PWD/server.py"`.
  A host with no LLM: browser UI -> Node proxy -> server over stdio. I play the model by clicking tools.
  The session token protects the proxy (it can start programs on my machine).
- Claude Desktop: Settings -> Desktop app -> Extensions -> Local MCP servers -> Edit config.
  File: `~/Library/Application Support/Claude/claude_desktop_config.json`. Logs: `~/Library/Logs/Claude/mcp*.log`.
- Config added next to the app's own `"preferences"` key:
```json
"mcpServers": {
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem",
             "/Users/app/ML AWS Road Map/ai-learning-journal/mcp-server/day-44/mcp-sandbox"]
  },
  "day44-hello": {
    "command": "/Users/app/ML AWS Road Map/ai-learning-journal/venv/bin/python",
    "args": ["/Users/app/ML AWS Road Map/ai-learning-journal/mcp-server/day-44/server.py"]
  }
}
```
- Filesystem server limited to one sandbox folder = least privilege (Day 47).

## Problems hit and fixes
| Problem | Cause | Fix |
|---|---|---|
| `pip install "mcp[cli]"` failed building `cryptography` | No wheel for cryptography 50 on Intel Mac + old pip 24.2 -> pip tried to compile (Rust + OpenSSL) | `pip install --upgrade pip` then `pip install --only-binary=cryptography "mcp[cli]"` -> cryptography 48.0.1 universal2 wheel |
| Inspector: `can't open file '/Users/app/ML'` | Inspector splits the Arguments box on spaces ("ML AWS Road Map") | Arguments = `server.py` (relative, launched from day-44) |
| `greeting` not in List Resources | It is a template, not a fixed resource | Resources tab -> List Templates |
| `MCP error -32601` | Inspector asked for autocomplete (`completion/complete`), server doesn't implement it | Harmless; close dropdown, Read Resource |
| Red squiggles in config | Extra `{ }` around `"mcpServers"` (object with no key) | `"mcpServers"` must be a key in the top-level object next to `"preferences"` |
| day44-hello: `No such file`, then `write EPIPE` | Path used `/mcp/` but folder is `/mcp-server/` | Correct path; check with `python3 -m json.tool <config>` |

Wheel = prebuilt package, installs instantly. sdist = source package, compiled during install.
Folder named `mcp-server` (not `mcp`) avoids shadowing the `mcp` package. Never add `__init__.py` or `mcp.py` there.

## Results (Claude Desktop, both servers Running)
| Prompt | What happened |
|---|---|
| Files in mcp-sandbox + read quote.txt | filesystem server: list directory, then read file (2 calls = ReAct loop over MCP). "Rate: 1200 USD, Fuel surcharge: 8%" |
| Add 17 and 25 | `add` -> 42 |
| Words in "the LLM reads, software decides" | `count_words` -> 5 (`the`, `LLM`, `reads,`, `software`, `decides`). My mentor guessed 6; the tool was right: software counts, the LLM reports |
| What tools from day44-hello? | Described `add` and `count_words` from my docstrings (= `tools/list` seen by the model) |

## Self-check answers
1. Claude Desktop is the host (with a client inside it); `server.py` is the server.
2. A stdio server waits for the host to send the first message on stdin, so it prints nothing. A traceback or instant exit would be the real bug.
3. From the function's docstring (and name). The model reads it to decide whether and when to call the tool, so vague wording = wrong or missed calls.
4. It has a `{name}` placeholder, so it is a resource template; templates are listed by `resources/templates/list`.
5. "Load invoice #123 to show the user" = resource (read-only data the app loads). "Recalculate the invoice total" = tool (computation the model asks for).
6. Function calling is how the model asks for an action; MCP is the standard for how the app discovers and runs that action in a separate program.
7. Claude Desktop starts the server in its own process without my shell's environment, so no activated venv and no current folder; only an absolute path to the venv's Python finds the `mcp` package and the script.

## Next (Day 45)
FreightLens MCP server (local): tool design (names, descriptions, Pydantic input/output schemas, recoverable errors),
read-only vs side-effect tools, resource for a document by id, prompt for explaining a discrepancy, unit tests.
