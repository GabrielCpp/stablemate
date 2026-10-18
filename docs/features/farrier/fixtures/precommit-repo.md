---
type: fixture
title: Pre-commit repo
---
# Pre-commit repo

A directory whose `agents.yml` has no `hooks:` key and that holds an empty `.pre-commit-config.yaml`.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' > "$dir/agents.yml"

### config

- kind: seed
- working-directory: scenario:
- run: touch "$dir/.pre-commit-config.yaml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
