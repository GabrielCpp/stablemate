"""MCP servers the library declares, and how each harness spells one in its home config."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from farrier._vendor.stablemate_core.schema import Selection
from farrier.layers import available_names, find_in_layers, searched_layers
from farrier.sources import load_pack, read_yaml

SERVER_KEYS = {"command", "args", "env"}
OPENCODE_CONFIG = ".config/opencode/opencode.json"


@dataclass(frozen=True)
class ToolServer:
    """One MCP server as the library declares it, in no harness's spelling."""

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


def claude_server(server: ToolServer) -> dict[str, Any]:
    return {
        "type": "stdio",
        "command": server.command,
        "args": server.args,
        "env": server.env,
    }


def codex_server(server: ToolServer) -> dict[str, Any]:
    spelled: dict[str, Any] = {"command": server.command, "args": server.args}
    if server.env:
        spelled["env"] = server.env
    return spelled


def copilot_server(server: ToolServer) -> dict[str, Any]:
    spelled: dict[str, Any] = {
        "type": "local",
        "command": server.command,
        "args": server.args,
    }
    if server.env:
        spelled["env"] = server.env
    spelled["tools"] = ["*"]
    return spelled


def opencode_server(server: ToolServer) -> dict[str, Any]:
    spelled: dict[str, Any] = {
        "type": "local",
        "command": [server.command, *server.args],
    }
    if server.env:
        spelled["environment"] = server.env
    return spelled


@dataclass(frozen=True)
class McpDialect:
    """Where one harness reads its home MCP servers, and how it spells one."""

    rel: str
    container: str
    spell: Callable[[ToolServer], dict[str, Any]]


MCP_DIALECTS = {
    "claude": McpDialect(".claude.json", "mcpServers", claude_server),
    "codex": McpDialect(".codex/config.toml", "mcp_servers", codex_server),
    "copilot": McpDialect(".copilot/mcp-config.json", "mcpServers", copilot_server),
    "opencode": McpDialect(OPENCODE_CONFIG, "mcp", opencode_server),
    "antigravity": McpDialect(
        ".gemini/config/mcp_config.json", "mcpServers", codex_server
    ),
    "pi": McpDialect(".pi/agent/mcp.json", "mcpServers", claude_server),
}


def load_tool_server(name: str) -> ToolServer:
    """The server record ``library/mcp/<name>.yml`` from the highest layer holding it."""
    hit = find_in_layers("library", "mcp", f"{name}.yml")
    if hit is None:
        available = (
            ", ".join(available_names("library", "mcp", suffix=".yml")) or "none"
        )
        raise SystemExit(
            f"error: unknown MCP server {name!r}. Available: {available}.\n"
            f"Searched these library layers:\n{searched_layers()}"
        )
    _layer, path = hit
    data = read_yaml(path)
    unknown = sorted(set(data) - SERVER_KEYS)
    if unknown:
        raise SystemExit(f"error: {path} has unknown keys: {', '.join(unknown)}.")
    command = data.get("command")
    if not isinstance(command, str) or not command:
        raise SystemExit(f"error: {path} needs a `command`.")
    return ToolServer(
        name,
        command,
        [str(arg) for arg in data.get("args") or []],
        {str(key): str(value) for key, value in (data.get("env") or {}).items()},
    )


def tool_server_names(table: Selection) -> set[str]:
    """The servers one harness table selects, directly or through its packs."""
    names = set(table.mcp)
    for pack in table.packs:
        names.update(load_pack(str(pack))["mcp"])
    return names
