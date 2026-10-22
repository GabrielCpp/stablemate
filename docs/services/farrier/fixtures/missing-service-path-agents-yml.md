---
type: fixture
title: Missing service path agents.yml
---
# Missing service path agents.yml

A directory whose `agents.yml` declares the service `api` at `app/api`, a path the directory does not hold.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'services: {api: {path: app/api, lint: ruff, test: pytest}}' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
