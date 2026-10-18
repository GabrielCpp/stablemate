---
type: fixture
title: One tree as both layers
---
# One tree as both layers

A library `overlay` named as both `library_dir` and `base_dir`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### overlay-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Only api"' --- '' 'Use it.' > "$dir/overlay/library/skills/stacks/api.md"

### overlay-packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/overlay/packs"

### config

- kind: seed
- working-directory: scenario:
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\nbase_dir = "%s"\n' "$PWD/$dir/overlay" "$PWD/$dir/overlay"; } > "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
