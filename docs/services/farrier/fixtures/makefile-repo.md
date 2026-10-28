---
type: fixture
title: Makefile repo
---
# Makefile repo

The demo skill repo plus a hand-written root `Makefile`.

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

### makefile

- kind: seed
- run: mkdir -p "$(dirname "$dir/Makefile")" && printf '%s\n' all: '	@true' > "$dir/Makefile"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
