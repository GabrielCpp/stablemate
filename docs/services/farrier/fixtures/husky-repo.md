---
type: fixture
title: Husky repo
---
# Husky repo

A directory whose `agents.yml` declares `hooks: {manager: husky}`. Its config names an empty base library `base-layer`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' 'hooks: {manager: husky}' > "$dir/agents.yml"

### library

- kind: seed
- run: mkdir -p "$dir/base-layer/library/skills" "$dir/base-layer/packs"

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base-layer"; } > "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
