---
type: fixture
title: Moved source skill
---
# Moved source skill

The generated demo skill with no `library/skills/demo/SKILL.md` in any layer.

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
- run: mkdir -p "$dir/library-dir/library/skills" "$dir/library-dir/packs" "$dir/base-layer/library/skills" "$dir/base-layer/packs"

### generated

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/.claude/skills/acme-demo/SKILL.md")" && printf '%s\n' --- 'name: acme-demo' 'description: "A skill."' metadata: '  name: demo' '  generated_by: farrier' '  source: library/skills/demo/SKILL.md' --- '' 'Use it.' > "$dir/.claude/skills/acme-demo/SKILL.md"

### config

- kind: seed
- working-directory: scenario:
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base-layer"; } > "$dir/config.toml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
