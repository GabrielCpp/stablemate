---
type: fixture
slug: agents-foreign-home
title: Hand-written agent home
---
# Hand-written agent home

A home holding a hand-written Claude agent under a name the Claude table selects, and another hand-written agent under a name it does not.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" "$dir/lib/packs" "$dir/lib/library/agents" && printf 'config_version = 2\n' > "$dir/config.toml"

### records

- kind: seed
- run: printf '%s\n' '---' 'description: Answers one narrow question.' 'read_only: true' '---' '' 'You answer one question.' > "$dir/lib/library/agents/lookup.md" && printf '%s\n' '---' 'description: Carries out a decided plan.' '---' '' 'You carry out a plan.' > "$dir/lib/library/agents/worker.md"

### profiles

- kind: seed
- run: printf '%s\n' '[profiles.claude]' 'cli = "claude"' '' '[profiles.claude.delegates.lookup]' 'model = "haiku-x"' '' '[profiles.claude.delegates.worker]' 'model = "sonnet-x"' '' '[profiles.codex]' 'cli = "codex"' '' '[profiles.codex.delegates.lookup]' 'model = "@luna"' '' '[profiles.codex.delegates.worker]' 'model = "terra"' '' >> "$dir/config.toml"

### tables

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'agents = ["lookup", "worker"]' '' '[user_library.codex]' 'agents = ["lookup", "worker"]' >> "$dir/config.toml"

### hand-written

- kind: seed
- run: mkdir -p "$dir/home/.claude/agents" && printf '%s\n' '---' 'name: lookup' '---' '' 'mine' > "$dir/home/.claude/agents/lookup.md" && printf '%s\n' '---' 'name: mine' '---' '' 'keep' > "$dir/home/.claude/agents/mine.md"

### landed

- kind: verify
- run: test -d "$dir"
