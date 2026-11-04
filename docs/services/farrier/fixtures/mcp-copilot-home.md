---
type: fixture
slug: mcp-copilot-home
title: Copilot MCP table home
---
# Copilot MCP table home

A Copilot table naming an MCP server.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home/.codex" "$dir/lib/packs" "$dir/lib/library/mcp" && printf 'config_version = 2\n' > "$dir/config.toml"

### server

- kind: seed
- run: printf '%s\n' 'command: /bin/true' 'args: ["--stub"]' > "$dir/lib/library/mcp/stub.yml"

### config

- kind: seed
- run: printf '%s\n' '[user_library.copilot]' 'mcp = ["stub"]' >> "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
