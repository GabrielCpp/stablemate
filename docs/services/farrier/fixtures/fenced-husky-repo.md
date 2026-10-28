---
type: fixture
title: Fenced husky repo
---
# Fenced husky repo

A directory whose `agents.yml` declares `hooks: {manager: none}` and whose `.husky/pre-commit` holds farrier's fenced hook entry, and its config names an empty base library `base-layer`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'hooks: {manager: none}' > "$dir/agents.yml"
- working-directory: scenario:

### husky

- kind: seed
- run: mkdir -p "$(dirname "$dir/.husky/pre-commit")" && printf '%s\n' '#!/bin/sh' '# >>> farrier: hooks (generated) >>>' 'make farrier-run-hook' '# <<< farrier: hooks <<<' > "$dir/.husky/pre-commit"
- working-directory: scenario:

### library

- kind: seed
- run: mkdir -p "$dir/base-layer/library/skills" "$dir/base-layer/packs"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base-layer"; } > "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
