---
type: fixture
title: Doubled skill repo
---
# Doubled skill repo

The demo skill repo with both Claude and Codex enabled as real (unlinked) harnesses, after `farrier install`, so the generated skill folder is duplicated under both.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-demo

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' '  codex: true' repo: '  name: acme' skills: '  - demo' > "$dir/agents.yml"

### install

- kind: seed
- working-directory: scenario:
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --repo "$dir" --library "$dir/lib"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
