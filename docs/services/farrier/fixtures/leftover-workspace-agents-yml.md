---
type: fixture
title: Leftover workspace agents.yml
---
# Leftover workspace agents.yml

A directory whose `agents.yml` still carries a `workspace:` section with the service root `api`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' workspace: '  service_roots: [api]' 'services: {api: {lint: ruff, test: pytest}}' > "$dir/agents.yml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
