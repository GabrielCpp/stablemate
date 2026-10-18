---
type: fixture
title: Stale skill repo
---
# Stale skill repo

The demo skill repo after `farrier install`, plus a farrier-tagged `.claude/skills/old/SKILL.md` the library no longer selects.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' skills: '  - demo' > "$dir/agents.yml"

### install

- kind: seed
- working-directory: scenario:
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --repo "$dir" --library "$dir/lib"

### stale

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/.claude/skills/old/SKILL.md")" && printf '%s\n' --- 'name: old' 'description: "Left behind."' metadata: '  name: old' '  generated_by: farrier' --- '' Old. > "$dir/.claude/skills/old/SKILL.md"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
