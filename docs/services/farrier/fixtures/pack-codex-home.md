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
- run: printf '%s\n' '[user_library.codex]' 'packs = ["general"]' >> "$dir/config.toml"
- working-directory: scenario:

### prompt

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/prompts/greet.md")" && printf '%s\n' --- 'description: "A prompt."' --- '' Ask. > "$dir/lib/library/prompts/greet.md"
- working-directory: scenario:

### pack

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/packs/general.yml")" && printf '%s\n' skills: '  - demo' prompts: '  - greet' > "$dir/lib/packs/general.yml"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
