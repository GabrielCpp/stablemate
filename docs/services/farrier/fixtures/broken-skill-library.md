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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api/SKILL.md")" && printf '%s\n' 'Body with no front matter.' > "$dir/overlay/library/skills/stacks/api/SKILL.md"
- working-directory: scenario:

### packs

- kind: seed
- run: mkdir -p "$dir/overlay/packs"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\n' "$PWD/$dir/overlay"; } > "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
