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
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/library-dir/library/skills" "$dir/library-dir/packs"

### agents-md

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/AGENTS.md")" && printf '%s\n' 'Aggregated rules.' > "$dir/AGENTS.md"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' localInstructions: '  - paths: ["."]' '    text: Rules.' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
