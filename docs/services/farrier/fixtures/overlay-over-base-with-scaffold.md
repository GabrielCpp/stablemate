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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### base-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/base/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Base api"' --- '' 'Use it.' > "$dir/base/library/skills/stacks/api.md"
- working-directory: scenario:

### base-packs

- kind: seed
- run: mkdir -p "$dir/base/packs"
- working-directory: scenario:

### overlay-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/overlay/library/skills/stacks/api.md")" && printf '%s\n' --- 'name: api' 'description: "Overlay api"' --- '' 'Use it.' > "$dir/overlay/library/skills/stacks/api.md"
- working-directory: scenario:

### overlay-packs

- kind: seed
- run: mkdir -p "$dir/overlay/packs"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'library_dir = "%s"\nbase_dir = "%s"\n' "$PWD/$dir/overlay" "$PWD/$dir/base"; } > "$dir/config.toml"
- working-directory: scenario:

### scaffold

- kind: seed
- run: mkdir -p "$(dirname "$dir/overlay/scaffolds/service-gitignore.yml")" && printf '%s\n' service-gitignore: '  params:' '    dir: api' '  tree:' '    $dir/.gitignore: |' '      node_modules' > "$dir/overlay/scaffolds/service-gitignore.yml"
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
