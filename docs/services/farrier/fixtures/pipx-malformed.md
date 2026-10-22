---
type: fixture
title: Malformed pipx output
---
# Malformed pipx output

A `pipx` stub that prints text which is not JSON.

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
- run: mkdir -p "$dir/pipx-stub-bin" && mkdir -p "$(dirname "$dir/pipx-stub-bin/pipx")" && printf '%s\n' '#!/bin/sh' 'printf '"'"'%s\n'"'"' '"'"'not json'"'"'' 'exit 0' > "$dir/pipx-stub-bin/pipx" && chmod +x "$dir/pipx-stub-bin/pipx"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
