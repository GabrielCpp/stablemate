---
type: fixture
title: Plain notes file
---
# Plain notes file

A `NOTES.md` holding one hand-written paragraph and no front matter, beside an empty library directory `library-dir` and a second empty layer named as the base.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/library-dir/library/skills" "$dir/library-dir/packs" "$dir/base-layer/library/skills" "$dir/base-layer/packs"

### notes

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/NOTES.md")" && printf '%s\n' 'One hand-written paragraph.' > "$dir/NOTES.md"

### config

- kind: seed
- working-directory: scenario:
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base-layer"; } > "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
