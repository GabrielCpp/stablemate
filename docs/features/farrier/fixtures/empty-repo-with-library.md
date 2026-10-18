---
type: fixture
title: Empty repo with library
---
# Empty repo with library

An empty git repository in `dir` and a library `lib` holding one skill.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### git

- kind: seed
- working-directory: scenario:
- run: git init -q "$dir"

### library-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/lib/packs"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
