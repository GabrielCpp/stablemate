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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### overlay-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Only api"' --- '' 'Use it.' > "$dir/overlay/library/skills/stacks/api.md"
- working-directory: scenario:

### overlay-packs

- kind: seed
- run: mkdir -p "$dir/overlay/packs"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\nbase_dir = "%s"\n' "$PWD/$dir/overlay" "$PWD/$dir/overlay"; } > "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
