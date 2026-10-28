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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' > "$dir/agents.yml"
- working-directory: scenario:

### config

- kind: seed
- run: touch "$dir/.pre-commit-config.yaml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
