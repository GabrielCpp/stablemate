---
type: fixture
title: Claude old skill home
---
# Claude old skill home

The user library home plus a farrier-tagged `home/.claude/skills/old/SKILL.md`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"
- working-directory: scenario:

### packs

- kind: seed
- run: mkdir -p "$dir/lib/packs"
- working-directory: scenario:

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'skills = ["demo"]' >> "$dir/config.toml"
- working-directory: scenario:

### old

- kind: seed
- run: mkdir -p "$(dirname "$dir/home/.claude/skills/old/SKILL.md")" && printf '%s\n' --- 'name: old' 'description: "Left behind."' metadata: '  name: old' '  generated_by: farrier' --- '' Old. > "$dir/home/.claude/skills/old/SKILL.md"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
