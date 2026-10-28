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
- run: printf '%s\n' '[user_library.codex]' 'prompts = ["demo-prompt"]' >> "$dir/config.toml"
- working-directory: scenario:

### prompt

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/prompts/demo-prompt.md")" && printf '%s\n' --- 'description: "A prompt."' --- '' Ask. > "$dir/lib/library/prompts/demo-prompt.md"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
