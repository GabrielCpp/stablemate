---
type: fixture
title: Policy skill repo
---
# Policy skill repo

A repo whose `localInstructions` entry lists the library policy `house-style` for path `.`, after `farrier install`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-policy

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/policies/house-style.md")" && printf '%s\n' --- 'name: house-style' 'description: "A policy."' --- '' 'Keep it consistent.' > "$dir/lib/library/policies/house-style.md"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' localInstructions: '  - policy: house-style' '    paths: ["."]' > "$dir/agents.yml"

### install

- kind: seed
- working-directory: scenario:
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --repo "$dir" --library "$dir/lib"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
