---
type: fixture
title: Two api skills
---
# Two api skills

A library `overlay` holding the skills `stacks/api`, installed as `stacks-api`, and `tools/api`, installed as `tools-api`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### stacks

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: stacks-api' 'description: "Stacks api"' --- '' 'Use it.' > "$dir/overlay/library/skills/stacks/api.md"

### tools

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/tools/api.md")" && printf '%s\n' --- 'name: tools-api' 'description: "Tools api"' --- '' 'Use it.' > "$dir/overlay/library/skills/tools/api.md"

### packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/overlay/packs"

### config

- kind: seed
- working-directory: scenario:
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\n' "$PWD/$dir/overlay"; } > "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
