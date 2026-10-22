---
type: fixture
title: User lefthook repo
---
# User lefthook repo

A directory whose `agents.yml` declares `hooks: {manager: lefthook}` and whose `lefthook.yml` holds a user-owned `pre-push:` block.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'hooks: {manager: lefthook}' > "$dir/agents.yml"

### lefthook

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lefthook.yml")" && printf '%s\n' pre-push: '  commands:' '    mine:' '      run: echo mine' > "$dir/lefthook.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
