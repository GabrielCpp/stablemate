---
type: fixture
slug: mcp-matching-home
title: Matching foreign MCP entry home
---
# Matching foreign MCP entry home

A skill-only Claude table, over a Claude state file that holds a server farrier did not install and that matches the library.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home/.codex" "$dir/lib/packs" "$dir/lib/library/mcp" && printf 'config_version = 2\n' > "$dir/config.toml"

### server

- kind: seed
- run: printf '%s\n' 'command: /bin/true' 'args: ["--stub"]' > "$dir/lib/library/mcp/stub.yml"

### skill

- kind: seed
- run: mkdir -p "$dir/lib/library/skills" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'skills = ["demo"]' >> "$dir/config.toml"

### matching

- kind: seed
- run: printf '{"mcpServers": {"stub": {"type": "stdio", "command": "/bin/true", "args": ["--stub"], "env": {}}}}\n' > "$dir/home/.claude.json"

### landed

- kind: verify
- run: test -d "$dir"
