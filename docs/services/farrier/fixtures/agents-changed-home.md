---
type: fixture
slug: agents-changed-home
title: Changed role model home
---
# Changed role model home

A home after an install wrote its agents, with the Codex profile since naming another model for `lookup`.

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

### install

- kind: seed
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --user --home "$dir/home" --library "$dir/lib"

### change

- kind: seed
- run: sed -i 's/@luna/@sol/' "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
