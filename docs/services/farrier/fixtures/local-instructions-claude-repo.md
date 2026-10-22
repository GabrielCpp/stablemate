---
type: fixture
title: Local instructions Claude repo
---
# Local instructions Claude repo

The local instructions repo with `claudeMd: true` on the entry.

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
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' skills: '  - demo' localInstructions: '  - skill: demo' '    paths: ["api"]' '    claudeMd: true' > "$dir/agents.yml"

### api

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/api"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
