---
type: fixture
title: Template home
---
# Template home

The user library home whose skill references `{{ template.backend }}` and whose config sets `[user_library.template]` `backend = "acme-value"`.

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
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Backed by {{ template.backend }}.' > "$dir/lib/library/skills/demo.md"

### packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/lib/packs"

### config

- kind: seed
- working-directory: scenario:
- run: printf '%s\n' '[user_library.claude]' 'skills = ["demo"]' '' '[user_library.template]' 'backend = "acme-value"' >> "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
