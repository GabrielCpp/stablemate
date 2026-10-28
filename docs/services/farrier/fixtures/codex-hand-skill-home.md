---
type: fixture
title: Codex hand-written skill home
---
# Codex hand-written skill home

The user library home plus a hand-written `home/.codex/skills/mine/SKILL.md`.

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

### hand

- kind: seed
- run: mkdir -p "$(dirname "$dir/home/.codex/skills/mine/SKILL.md")" && printf '%s\n' --- 'name: mine' 'description: "Mine."' --- '' 'Hand written.' > "$dir/home/.codex/skills/mine/SKILL.md"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
