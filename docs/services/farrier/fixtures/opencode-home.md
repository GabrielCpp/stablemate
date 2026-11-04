---
type: fixture
slug: opencode-home
title: OpenCode home
---
# OpenCode home

An OpenCode table naming a skill, a root, a server, a guard and a read-only agent, in a home whose `opencode.jsonc` holds a comment and another server.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home/.config/opencode" "$dir/lib/packs" "$dir/lib/library/agents" "$dir/lib/library/mcp" "$dir/lib/library/roots" "$dir/lib/library/hooks/stub" "$dir/lib/library/skills/note" && printf 'config_version = 2\n' > "$dir/config.toml"

### records

- kind: seed
- run: printf '%s\n' '---' 'description: Answers one narrow question.' 'read_only: true' '---' '' 'You answer one question.' > "$dir/lib/library/agents/lookup.md" && printf '%s\n' 'command: ostler' 'args: [mcp]' > "$dir/lib/library/mcp/search.yml" && printf '%s\n' '---' 'description: Rules.' '---' '' 'Say hello.' > "$dir/lib/library/roots/rules.md" && printf '%s\n' 'command: sh {dir}/check.sh' 'watches: [shell, edit]' > "$dir/lib/library/hooks/stub/hook.yml" && printf '%s\n' 'exit 0' > "$dir/lib/library/hooks/stub/check.sh" && printf '%s\n' '---' 'name: note' 'description: A note.' '---' '' 'body' > "$dir/lib/library/skills/note/SKILL.md"

### table

- kind: seed
- run: printf '%s\n' '[profiles.opencode]' 'cli = "opencode"' '' '[profiles.opencode.delegates.lookup]' 'model = "kimi/k3"' '' '[user_library.opencode]' 'skills = ["note"]' 'roots = ["rules"]' 'mcp = ["search"]' 'hooks = ["stub"]' 'agents = ["lookup"]' >> "$dir/config.toml"

### own-config

- kind: seed
- run: printf '%s\n' '{' '  // my settings' '  "model": "kimi/k3",' '  "mcp": {"playwright": {"type": "local", "command": ["npx"]},},' '}' > "$dir/home/.config/opencode/opencode.jsonc"

### landed

- kind: verify
- run: test -d "$dir"
