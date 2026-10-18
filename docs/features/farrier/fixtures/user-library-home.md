---
type: fixture
title: User library home
---
# User library home

A library `lib` with one skill `demo` and a config holding `[user_library.claude]` with `skills = ["demo"]`. The home directory `home` is empty.

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
- run: printf '%s\n' '[user_library.claude]' 'skills = ["demo"]' >> "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
