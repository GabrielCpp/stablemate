---
type: fixture
slug: guards-foreign-home
title: Foreign guard home
---
# Foreign guard home

A Claude table naming a guard, over Claude settings that already run the same command on other tools.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home/.claude" "$dir/lib/packs" "$dir/lib/library/hooks/stub" && printf 'config_version = 2\n' > "$dir/config.toml"

### guard

- kind: seed
- run: printf '%s\n' 'command: /bin/true --stub' 'watches: [shell]' > "$dir/lib/library/hooks/stub/hook.yml"

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'hooks = ["stub"]' >> "$dir/config.toml"

### foreign

- kind: seed
- run: printf '{"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "/bin/true --stub"}]}]}}\n' > "$dir/home/.claude/settings.json"

### landed

- kind: verify
- run: test -d "$dir"
