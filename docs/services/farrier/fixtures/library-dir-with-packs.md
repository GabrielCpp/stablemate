---
type: fixture
title: Library directory with packs
---
# Library directory with packs

A directory `lib` holding `library/` and `packs/`.

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

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
