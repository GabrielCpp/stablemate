---
type: fixture
title: No agents repo
---
# No agents repo

A directory whose `agents.yml` has an `agents:` mapping that enables nothing, next to an empty library `lib`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library

- kind: seed
- run: mkdir -p "$dir/lib/library" "$dir/lib/packs"

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'agents: {}' > "$dir/agents.yml"

### landed

- kind: verify
- run: test -d "$dir"
