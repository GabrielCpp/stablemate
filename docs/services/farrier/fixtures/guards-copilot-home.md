---
type: fixture
slug: guards-copilot-home
title: Copilot guard table home
---
# Copilot guard table home

A Copilot table naming a guard.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" "$dir/lib/packs" "$dir/lib/library/hooks/stub" && printf 'config_version = 2\n' > "$dir/config.toml"

### guard

- kind: seed
- run: printf '%s\n' 'command: /bin/true --stub' 'watches: [shell]' > "$dir/lib/library/hooks/stub/hook.yml"

### config

- kind: seed
- run: printf '%s\n' '[user_library.copilot]' 'hooks = ["stub"]' >> "$dir/config.toml"

### landed

- kind: verify
- run: test -d "$dir"
