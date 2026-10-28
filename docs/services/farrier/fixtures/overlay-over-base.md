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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### base-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/base/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Base api"' --- '' 'Use it.' > "$dir/base/library/skills/stacks/api.md"
- working-directory: scenario:

### base-packs

- kind: seed
- run: mkdir -p "$dir/base/packs"
- working-directory: scenario:

### overlay-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Overlay api"' --- '' 'Use it.' > "$dir/overlay/library/skills/stacks/api.md"
- working-directory: scenario:

### overlay-packs

- kind: seed
- run: mkdir -p "$dir/overlay/packs"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\nbase_dir = "%s"\n' "$PWD/$dir/overlay" "$PWD/$dir/base"; } > "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
