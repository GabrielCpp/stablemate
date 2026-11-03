---
type: fixture
title: Codex and Copilot home
---
# Codex and Copilot home

The user library home with `[user_library.codex]` and `[user_library.copilot]` tables that both select `demo`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### packs

- kind: seed
- run: mkdir -p "$dir/lib/packs"

### config

- kind: seed
- run: printf '%s\n' '[user_library.codex]' 'skills = ["demo"]' '' '[user_library.copilot]' 'skills = ["demo"]' >> "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
