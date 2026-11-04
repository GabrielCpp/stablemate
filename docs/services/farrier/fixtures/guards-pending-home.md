---
type: fixture
slug: guards-pending-home
title: Guard waiting for approval
---
# Guard waiting for approval

A home after an install wrote its guards, with no approval recorded in the Codex config.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home/.codex" "$dir/lib/packs" "$dir/lib/library/hooks/stub/tests" "$dir/lib/library/hooks/claude-only" && printf 'config_version = 2\n' > "$dir/config.toml"

### guards

- kind: seed
- run: printf '%s\n' 'command: python3 {dir}/check.py' 'watches: [shell, edit]' 'status: Checking' > "$dir/lib/library/hooks/stub/hook.yml" && printf 'print("stub guard")\n' > "$dir/lib/library/hooks/stub/check.py" && printf 'print("stub test")\n' > "$dir/lib/library/hooks/stub/tests/test_check.py"

### claude-only

- kind: seed
- run: printf '%s\n' 'command: /bin/true --claude-only' 'watches: [shell]' 'not_on: [codex]' > "$dir/lib/library/hooks/claude-only/hook.yml"

### codex-config

- kind: seed
- run: printf '%s\n' '# my settings' 'model = "gpt"' > "$dir/home/.codex/config.toml"

### config

- kind: seed
- run: printf '%s\n' '[user_library.claude]' 'hooks = ["stub", "claude-only"]' '' '[user_library.codex]' 'hooks = ["stub", "claude-only"]' >> "$dir/config.toml"

### install

- kind: seed
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --user --home "$dir/home" --library "$dir/lib"

### landed

- kind: verify
- run: test -d "$dir"
