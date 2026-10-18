---
type: fixture
title: Roots repo
---
# Roots repo

The demo skill repo with Copilot enabled, a library root `house` and `roots: [house]`.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' '  copilot: true' repo: '  name: acme' skills: '  - demo' roots: '  - house' > "$dir/agents.yml"

### root

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/roots/house.md")" && printf '%s\n' --- 'description: "House rules."' --- '' 'Be tidy.' > "$dir/lib/library/roots/house.md"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
