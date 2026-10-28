---
type: fixture
title: Text instructions AGENTS.md
---
# Text instructions AGENTS.md

An `AGENTS.md` without front matter and an `agents.yml` whose `localInstructions` entry carries a `text` value.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library

- kind: seed
- run: mkdir -p "$dir/library-dir/library/skills" "$dir/library-dir/packs"
- working-directory: scenario:

### agents-md

- kind: seed
- run: mkdir -p "$(dirname "$dir/AGENTS.md")" && printf '%s\n' 'Aggregated rules.' > "$dir/AGENTS.md"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' localInstructions: '  - paths: ["."]' '    text: Rules.' > "$dir/agents.yml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
