---
type: fixture
title: Githooks repo
---
# Githooks repo

An initialised git repository in `dir` whose `agents.yml` declares `hooks: {manager: githooks}`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### git

- kind: seed
- working-directory: scenario:
- run: git init -q "$dir"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'hooks: {manager: githooks}' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
