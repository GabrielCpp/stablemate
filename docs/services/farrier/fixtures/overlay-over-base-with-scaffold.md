---
type: fixture
title: Overlay over base with a scaffold
---
# Overlay over base with a scaffold

The overlay over base layers plus a scaffold `service-gitignore` in the overlay, a repo `agents.yml` listing it and a hand-written file at one scaffold path.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### base-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/base/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Base api"' --- '' 'Use it.' > "$dir/base/library/skills/stacks/api.md"

### base-packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/base/packs"

### overlay-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Overlay api"' --- '' 'Use it.' > "$dir/overlay/library/skills/stacks/api.md"

### overlay-packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/overlay/packs"

### config

- kind: seed
- working-directory: scenario:
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\nbase_dir = "%s"\n' "$PWD/$dir/overlay" "$PWD/$dir/base"; } > "$dir/config.toml"

### scaffold

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/overlay/scaffolds/service-gitignore.yml")" && printf '%s\n' service-gitignore: '  params:' '    dir: api' '  tree:' '    $dir/.gitignore: |' '      node_modules' > "$dir/overlay/scaffolds/service-gitignore.yml"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' scaffolds: '  - service-gitignore' > "$dir/agents.yml"

### existing

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/api/.gitignore")" && printf '%s\n' 'hand edited' > "$dir/api/.gitignore"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
