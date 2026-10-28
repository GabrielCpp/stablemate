---
type: fixture
title: Excluded skill repo
---
# Excluded skill repo

The demo skill repo that selects the library skill `other` and then lists it under `exclude:`.

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

### library-other

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/other.md")" && printf '%s\n' --- 'name: other' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/other.md"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' skills: '  - demo' '  - other' exclude: '  skills:' '    - other' > "$dir/agents.yml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
