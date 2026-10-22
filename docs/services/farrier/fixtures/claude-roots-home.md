---
type: fixture
title: Claude roots home
---
# Claude roots home

A library shipping the root `demo-root`, with `[user_library.claude]` selecting it under `roots`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/lib/packs"

### config

- kind: seed
- working-directory: scenario:
- run: printf '%s\n' '[user_library.claude]' 'roots = ["demo-root"]' >> "$dir/config.toml"

### root

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/roots/demo-root.md")" && printf '%s\n' --- 'description: "A root."' --- '' Rules. > "$dir/lib/library/roots/demo-root.md"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
