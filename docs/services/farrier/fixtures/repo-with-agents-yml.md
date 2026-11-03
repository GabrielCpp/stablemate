---
type: fixture
title: Repo with agents.yml
---
# Repo with agents.yml

A git repository in `dir` holding an `agents.yml` that enables Claude and selects no packs.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' 'packs: []' > "$dir/agents.yml"

### landed

- kind: verify
- run: test -d "$dir"
