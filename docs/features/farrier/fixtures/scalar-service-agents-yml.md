---
type: fixture
title: Scalar service agents.yml
---
# Scalar service agents.yml

A directory whose `agents.yml` declares `services: {api: lint}`, a service entry that is not a mapping.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'services: {api: lint}' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
