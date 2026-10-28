---
type: fixture
title: Scaffold library without agents.yml
---
# Scaffold library without agents.yml

The scaffold library in a directory with no `agents.yml`.

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

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
