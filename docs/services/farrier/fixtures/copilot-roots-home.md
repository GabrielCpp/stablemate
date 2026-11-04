---
type: fixture
title: Copilot roots home
---
# Copilot roots home

A library shipping the root `demo-root`, with `[user_library.copilot]` selecting it under `roots`.

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
- run: printf '%s\n' '[user_library.copilot]' 'roots = ["demo-root"]' >> "$dir/config.toml"

### root

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/roots/demo-root.md")" && printf '%s\n' --- 'description: "A root."' --- '' Rules. > "$dir/lib/library/roots/demo-root.md"

### landed

- kind: verify
- run: test -d "$dir"
