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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"
- working-directory: scenario:

### packs

- kind: seed
- run: mkdir -p "$dir/lib/packs"
- working-directory: scenario:

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'roots = ["demo-root"]' >> "$dir/config.toml"
- working-directory: scenario:

### root

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/roots/demo-root.md")" && printf '%s\n' --- 'description: "A root."' --- '' Rules. > "$dir/lib/library/roots/demo-root.md"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
