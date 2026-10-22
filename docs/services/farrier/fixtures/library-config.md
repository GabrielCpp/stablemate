---
type: fixture
title: Library config
---
# Library config

A config file `c.toml` in `dir` holding a `library_dir` setting.

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
- run: mkdir -p "$dir/lib/library" "$dir/lib/packs"

### config

- kind: seed
- working-directory: scenario:
- run: printf 'library_dir = "%s"\n' "$PWD/$dir/lib" > "$dir/c.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
