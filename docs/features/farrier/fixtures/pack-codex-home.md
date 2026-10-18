---
type: fixture
title: Pack Codex home
---
# Pack Codex home

A library with a skill `demo`, a prompt `greet` and a pack `general` naming both, with `[user_library.codex]` selecting `packs = ["general"]`.

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
- run: printf '%s\n' '[user_library.codex]' 'packs = ["general"]' >> "$dir/config.toml"

### prompt

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/prompts/greet.md")" && printf '%s\n' --- 'description: "A prompt."' --- '' Ask. > "$dir/lib/library/prompts/greet.md"

### pack

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/packs/general.yml")" && printf '%s\n' skills: '  - demo' prompts: '  - greet' > "$dir/lib/packs/general.yml"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
