---
type: fixture
title: Other config repo
---
# Other config repo

The demo skill repo with its `agents.yml` renamed to `other.yml`.

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

### rename

- kind: seed
- working-directory: scenario:
- run: mv "$dir/agents.yml" "$dir/other.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
