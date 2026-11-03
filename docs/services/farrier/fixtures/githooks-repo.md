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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### git

- kind: seed
- run: git init -q "$dir"

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'hooks: {manager: githooks}' > "$dir/agents.yml"

### landed

- kind: verify
- run: test -d "$dir"
