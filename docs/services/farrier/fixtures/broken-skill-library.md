---
type: fixture
title: Broken skill library
---
# Broken skill library

A library whose `stacks/api/SKILL.md` has no front matter block.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api/SKILL.md")" && printf '%s\n' 'Body with no front matter.' > "$dir/overlay/library/skills/stacks/api/SKILL.md"

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
