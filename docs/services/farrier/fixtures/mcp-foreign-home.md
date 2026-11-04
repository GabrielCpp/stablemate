---
type: fixture
slug: mcp-foreign-home
title: Foreign MCP entry home
---
# Foreign MCP entry home

A Claude and a Codex table naming one MCP server, over a Claude state file that already holds another value under that name.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home/.codex" "$dir/lib/packs" "$dir/lib/library/mcp" && printf 'config_version = 2\n' > "$dir/config.toml"

### server

- kind: seed
- run: printf '%s\n' 'command: /bin/true' 'args: ["--stub"]' > "$dir/lib/library/mcp/stub.yml"

### codex-config

- kind: seed
- run: printf '%s\n' '# my settings' 'model = "gpt"' '' '[mcp_servers.node_repl]' 'command = "node"' > "$dir/home/.codex/config.toml"

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'mcp = ["stub"]' '' '[user_library.codex]' 'mcp = ["stub"]' >> "$dir/config.toml"

### foreign

- kind: seed
- run: printf '{"mcpServers": {"stub": {"command": "mine"}}}\n' > "$dir/home/.claude.json"

### landed

- kind: verify
- run: test -d "$dir"
