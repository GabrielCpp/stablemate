---
type: fixture
title: Bare agents repo
---
# Bare agents repo

A directory whose `agents.yml` enables Claude and selects no pack, skill or prompt, next to an empty library `lib`.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' > "$dir/agents.yml"

### landed

- kind: verify
- run: test -d "$dir"
