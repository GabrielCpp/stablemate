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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'hooks: {manager: lefthook}' > "$dir/agents.yml"
- working-directory: scenario:

### lefthook

- kind: seed
- run: mkdir -p "$(dirname "$dir/lefthook.yml")" && printf '%s\n' pre-push: '  commands:' '    mine:' '      run: echo mine' > "$dir/lefthook.yml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
