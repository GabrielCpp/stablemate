---
type: fixture
title: Failing pipx
---
# Failing pipx

A `pipx` stub that exits 1.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### pipx-stub

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/pipx-stub-bin" && mkdir -p "$(dirname "$dir/pipx-stub-bin/pipx")" && printf '%s\n' '#!/bin/sh' 'printf '"'"'%s\n'"'"' '"'"''"'"'' 'exit 1' > "$dir/pipx-stub-bin/pipx" && chmod +x "$dir/pipx-stub-bin/pipx"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
