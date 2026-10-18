---
type: fixture
title: Codex old skill home
---
# Codex old skill home

The user library home plus a farrier-tagged `home/.codex/skills/old/SKILL.md`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-skill

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### packs

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$dir/lib/packs"

### config

- kind: seed
- working-directory: scenario:
- run: printf '%s\n' '[user_library.claude]' 'skills = ["demo"]' >> "$dir/config.toml"

### old

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/home/.codex/skills/old/SKILL.md")" && printf '%s\n' --- 'name: old' 'description: "Left behind."' metadata: '  name: old' '  generated_by: farrier' --- '' Old. > "$dir/home/.codex/skills/old/SKILL.md"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
