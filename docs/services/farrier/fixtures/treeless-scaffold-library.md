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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library

- kind: seed
- run: mkdir -p "$dir/scaffold-library/library/skills" "$dir/scaffold-library/packs"
- working-directory: scenario:

### scaffold-service-gitignore

- kind: seed
- run: mkdir -p "$(dirname "$dir/scaffold-library/scaffolds/service-gitignore.yml")" && printf '%s\n' bad: '  description: No tree' > "$dir/scaffold-library/scaffolds/service-gitignore.yml"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' scaffolds: '  - bad' > "$dir/agents.yml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
