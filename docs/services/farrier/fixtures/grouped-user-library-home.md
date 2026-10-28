---
type: fixture
title: Grouped user library home
---
# Grouped user library home

The user library home with the skill `acme/demo` selected instead of `demo`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/acme/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/acme/demo.md"
- working-directory: scenario:

### packs

- kind: seed
- run: mkdir -p "$dir/lib/packs"
- working-directory: scenario:

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'skills = ["acme/demo"]' >> "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
