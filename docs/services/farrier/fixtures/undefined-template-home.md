---
type: fixture
title: Undefined template home
---
# Undefined template home

The user library home whose skill references `{{ template.backend }}` while the config sets no template table.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Backed by {{ template.backend }}.' > "$dir/lib/library/skills/demo.md"

### packs

- kind: seed
- run: mkdir -p "$dir/lib/packs"

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'skills = ["demo"]' >> "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
