---
type: fixture
title: Orphan root agents.yml
---
# Orphan root agents.yml

A directory whose `agents.yml` lists the service root `web` and declares only the service `api`.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' workspace: '  service_roots: [web]' 'services: {api: {lint: ruff, test: pytest}}' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
