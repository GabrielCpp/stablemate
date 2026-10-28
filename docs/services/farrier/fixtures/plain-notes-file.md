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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library

- kind: seed
- run: mkdir -p "$dir/library-dir/library/skills" "$dir/library-dir/packs" "$dir/base-layer/library/skills" "$dir/base-layer/packs"
- working-directory: scenario:

### notes

- kind: seed
- run: mkdir -p "$(dirname "$dir/NOTES.md")" && printf '%s\n' 'One hand-written paragraph.' > "$dir/NOTES.md"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base-layer"; } > "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
