---
type: fixture
title: Aggregated AGENTS.md
---
# Aggregated AGENTS.md

The generated demo skill layout plus an `AGENTS.md` without front matter and an `agents.yml` whose `localInstructions` entry selects the skill.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library

- kind: seed
- run: mkdir -p "$dir/library-dir/library/skills" "$dir/library-dir/packs" "$dir/base-layer/library/skills" "$dir/base-layer/packs"
- working-directory: scenario:

### source

- kind: seed
- run: mkdir -p "$(dirname "$dir/library-dir/library/skills/demo/SKILL.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/library-dir/library/skills/demo/SKILL.md"
- working-directory: scenario:

### generated

- kind: seed
- run: mkdir -p "$(dirname "$dir/.claude/skills/acme-demo/SKILL.md")" && printf '%s\n' --- 'name: acme-demo' 'description: "A skill."' metadata: '  name: demo' '  generated_by: farrier' '  source: library/skills/demo/SKILL.md' --- '' 'Use it.' > "$dir/.claude/skills/acme-demo/SKILL.md"
- working-directory: scenario:

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base-layer"; } > "$dir/config.toml"
- working-directory: scenario:

### agents-md

- kind: seed
- run: mkdir -p "$(dirname "$dir/AGENTS.md")" && printf '%s\n' 'Aggregated rules.' > "$dir/AGENTS.md"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' 'repo: {name: acme}' skills: '  - demo' localInstructions: '  - skill: demo' '    paths: ["."]' > "$dir/agents.yml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
