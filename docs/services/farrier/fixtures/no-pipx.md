---
type: fixture
title: No workflows from pipx
---
# No workflows from pipx

A `pipx` stub that lists no distribution. The claim puts `pipx-stub-bin` first on PATH, so this stands in for a machine with no `pipx` installed.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### pipx-stub

- kind: seed
- run: mkdir -p "$dir/pipx-stub-bin" && mkdir -p "$(dirname "$dir/pipx-stub-bin/pipx")" && printf '%s\n' '#!/bin/sh' 'printf '"'"'%s\n'"'"' '"'"'{"pipx_spec_version":"0.1","venvs":{}}'"'"'' 'exit 0' > "$dir/pipx-stub-bin/pipx" && chmod +x "$dir/pipx-stub-bin/pipx"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
