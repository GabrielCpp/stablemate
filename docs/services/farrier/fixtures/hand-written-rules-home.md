---
type: fixture
title: Hand-written rules home
---
# Hand-written rules home

A `[user_library.claude]` table selecting a root, over a home whose `~/.claude/CLAUDE.md` is hand written.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-skill

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### packs

- kind: seed
- run: mkdir -p "$dir/lib/packs"

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'roots = ["demo-root"]' >> "$dir/config.toml"

### root

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/roots/demo-root.md")" && printf '%s\n' --- 'description: "A root."' --- '' Rules. > "$dir/lib/library/roots/demo-root.md"

### hand-written

- kind: seed
- run: mkdir -p "$dir/home/.claude" && printf 'My rules.\n' > "$dir/home/.claude/CLAUDE.md"

### landed

- kind: verify
- run: test -d "$dir"
