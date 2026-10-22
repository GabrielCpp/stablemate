---
type: fixture
title: Codex prompts home
---
# Codex prompts home

A library shipping the prompt `demo-prompt`, with `[user_library.codex]` selecting it under `prompts`.

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
- run: printf '%s\n' '[user_library.codex]' 'prompts = ["demo-prompt"]' >> "$dir/config.toml"

### prompt

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/prompts/demo-prompt.md")" && printf '%s\n' --- 'description: "A prompt."' --- '' Ask. > "$dir/lib/library/prompts/demo-prompt.md"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
