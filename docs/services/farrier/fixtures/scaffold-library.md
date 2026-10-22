---
type: fixture
title: Scaffold library
---
# Scaffold library

A library `scaffold-library` whose `scaffolds/` holds `service-gitignore`, and a repo `agents.yml` listing it under `scaffolds:`. The scaffold takes the parameter `dir` with default `api` and writes `$dir/.gitignore`.

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
- run: mkdir -p "$(dirname "$dir/scaffold-library/scaffolds/service-gitignore.yml")" && printf '%s\n' service-gitignore: '  params:' '    dir: api' '  tree:' '    $dir/.gitignore: |' '      node_modules' > "$dir/scaffold-library/scaffolds/service-gitignore.yml"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' scaffolds: '  - service-gitignore' > "$dir/agents.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
