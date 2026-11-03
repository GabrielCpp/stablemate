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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library

- kind: seed
- run: mkdir -p "$dir/lib/library" "$dir/lib/packs"

### config

- kind: seed
- run: printf 'library_dir = "%s"\n' "$PWD/$dir/lib" > "$dir/c.toml"

### landed

- kind: verify
- run: test -d "$dir"
