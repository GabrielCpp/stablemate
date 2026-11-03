---
type: fixture
title: Generated demo skill
---
# Generated demo skill

A library directory `library-dir` holding `library/skills/demo/SKILL.md`, a second empty layer named as the base, and a generated `.claude/skills/acme-demo/SKILL.md` whose `metadata.source` is `library/skills/demo/SKILL.md`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library

- kind: seed
- run: mkdir -p "$dir/library-dir/library/skills" "$dir/library-dir/packs" "$dir/base-layer/library/skills" "$dir/base-layer/packs"

### source

- kind: seed
- run: mkdir -p "$(dirname "$dir/library-dir/library/skills/demo/SKILL.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/library-dir/library/skills/demo/SKILL.md"

### generated

- kind: seed
- run: mkdir -p "$(dirname "$dir/.claude/skills/acme-demo/SKILL.md")" && printf '%s\n' --- 'name: acme-demo' 'description: "A skill."' metadata: '  name: demo' '  generated_by: farrier' '  source: library/skills/demo/SKILL.md' --- '' 'Use it.' > "$dir/.claude/skills/acme-demo/SKILL.md"

### config

- kind: seed
- run: { printf 'config_version = 2\n'; printf 'base_dir = "%s"\n' "$PWD/$dir/base-layer"; } > "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
