---
type: fixture
title: Overlay over base
---
# Overlay over base

A base library `base` and an overlay library `overlay`, both holding the skill `stacks/api`, with the config in `dir` naming them as `base_dir` and `library_dir`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### base-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/base/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Base api"' --- '' 'Use it.' > "$dir/base/library/skills/stacks/api.md"

### base-packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/base/packs"

### overlay-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Overlay api"' --- '' 'Use it.' > "$dir/overlay/library/skills/stacks/api.md"

### overlay-packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/overlay/packs"

### config

- kind: seed
- working-directory: scenario:
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\nbase_dir = "%s"\n' "$PWD/$dir/overlay" "$PWD/$dir/base"; } > "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
