---
type: fixture
title: Overlay install repo
---
# Overlay install repo

The demo skill repo whose library `lib` also provides a skill the base library provides, with the config in `dir` naming that base library.

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

### base

- kind: seed
- run: mkdir -p "$(dirname "$dir/base/library/skills/acme/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "Base."' --- '' 'Base body.' > "$dir/base/library/skills/acme/demo.md"
- working-directory: scenario:

### base-packs

- kind: seed
- run: mkdir -p "$dir/base/packs"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base"; } > "$dir/config.toml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
