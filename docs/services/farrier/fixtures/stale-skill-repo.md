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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library-demo

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' skills: '  - demo' > "$dir/agents.yml"
- working-directory: scenario:

### install

- kind: seed
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --repo "$dir" --library "$dir/lib"
- working-directory: scenario:

### stale

- kind: seed
- run: mkdir -p "$(dirname "$dir/.claude/skills/old/SKILL.md")" && printf '%s\n' --- 'name: old' 'description: "Left behind."' metadata: '  name: old' '  generated_by: farrier' --- '' Old. > "$dir/.claude/skills/old/SKILL.md"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
