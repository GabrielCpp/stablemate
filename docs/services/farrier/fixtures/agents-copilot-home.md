---
type: fixture
slug: agents-copilot-home
title: Copilot agent table home
---
# Copilot agent table home

A Copilot table naming an agent.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" "$dir/lib/packs" "$dir/lib/library/agents" && printf 'config_version = 2\n' > "$dir/config.toml"

### records

- kind: seed
- run: printf '%s\n' '---' 'description: Answers one narrow question.' 'read_only: true' '---' '' 'You answer one question.' > "$dir/lib/library/agents/lookup.md" && printf '%s\n' '---' 'description: Carries out a decided plan.' '---' '' 'You carry out a plan.' > "$dir/lib/library/agents/worker.md"

### config

- kind: seed
- run: printf '%s\n' '[user_library.copilot]' 'agents = ["lookup"]' >> "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
