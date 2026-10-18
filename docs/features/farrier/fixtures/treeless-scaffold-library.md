---
type: fixture
title: Treeless scaffold library
---
# Treeless scaffold library

A library whose scaffold `bad` has a description and no `tree:`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/scaffold-library/library/skills" "$dir/scaffold-library/packs"

### scaffold-service-gitignore

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/scaffold-library/scaffolds/service-gitignore.yml")" && printf '%s\n' bad: '  description: No tree' > "$dir/scaffold-library/scaffolds/service-gitignore.yml"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' scaffolds: '  - bad' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
