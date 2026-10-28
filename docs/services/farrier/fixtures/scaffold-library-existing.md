---
type: fixture
title: Scaffold library with an existing file
---
# Scaffold library with an existing file

The scaffold library plus a hand-edited `api/.gitignore` in the repo.

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
- run: mkdir -p "$(dirname "$dir/scaffold-library/scaffolds/service-gitignore.yml")" && printf '%s\n' service-gitignore: '  params:' '    dir: api' '  tree:' '    $dir/.gitignore: |' '      node_modules' > "$dir/scaffold-library/scaffolds/service-gitignore.yml"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' scaffolds: '  - service-gitignore' > "$dir/agents.yml"
- working-directory: scenario:

### existing

- kind: seed
- run: mkdir -p "$(dirname "$dir/api/.gitignore")" && printf '%s\n' 'hand edited' > "$dir/api/.gitignore"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
