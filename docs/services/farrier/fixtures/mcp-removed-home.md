---
type: fixture
slug: mcp-removed-home
title: Dropped MCP server home
---
# Dropped MCP server home

A skill-only Claude table, over a home whose ledger records a server the table no longer names, beside a server of the user's own.

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

### claude-state

- kind: seed
- run: printf '{"mcpServers": {"stub": {"command": "/bin/true"}, "mine": {"command": "kept"}}}\n' > "$dir/home/.claude.json"

### ledger

- kind: seed
- run: mkdir -p "$dir/home/.agents" && printf '{".claude.json": {"mcpServers": ["stub"]}}\n' > "$dir/home/.agents/.farrier-home.json"

### landed

- kind: verify
- run: test -d "$dir"
