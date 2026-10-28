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

### held-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/.claude/skills/acme-demo/SKILL.md")" && printf '%s\n' 'hand written' > "$dir/.claude/skills/acme-demo/SKILL.md"
- working-directory: scenario:

### held-mk

- kind: seed
- run: mkdir -p "$(dirname "$dir/.agents/agents.mk")" && printf '%s\n' '# hand written' > "$dir/.agents/agents.mk"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
