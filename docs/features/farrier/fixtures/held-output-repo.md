---
type: fixture
title: Held output repo
---
# Held output repo

The demo skill repo plus a hand-written `.claude/skills/acme-demo/SKILL.md` and a hand-written `.agents/agents.mk`, both at paths an install renders.

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

### held-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/.claude/skills/acme-demo/SKILL.md")" && printf '%s\n' 'hand written' > "$dir/.claude/skills/acme-demo/SKILL.md"

### held-mk

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/.agents/agents.mk")" && printf '%s\n' '# hand written' > "$dir/.agents/agents.mk"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
