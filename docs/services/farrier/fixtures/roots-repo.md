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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library-demo

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' '  copilot: true' repo: '  name: acme' skills: '  - demo' roots: '  - house' > "$dir/agents.yml"
- working-directory: scenario:

### root

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/roots/house.md")" && printf '%s\n' --- 'description: "House rules."' --- '' 'Be tidy.' > "$dir/lib/library/roots/house.md"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
