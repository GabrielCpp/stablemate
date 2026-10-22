---
type: fixture
title: Declared pre-commit repo
---
# Declared pre-commit repo

A directory whose `agents.yml` declares `hooks: {manager: pre-commit}` and that holds no `.pre-commit-config.yaml`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'hooks: {manager: pre-commit}' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
