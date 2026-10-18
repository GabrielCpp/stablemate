---
type: fixture
title: No library layers
---
# No library layers

An empty config in `dir`, no library path and no base library installed.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
