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
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"
- working-directory: scenario:

### library-policy

- kind: seed
- run: mkdir -p "$(dirname "$dir/lib/library/policies/house-style.md")" && printf '%s\n' --- 'name: house-style' 'description: "A policy."' --- '' 'Keep it consistent.' > "$dir/lib/library/policies/house-style.md"
- working-directory: scenario:

### agents-yml

- kind: seed
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' localInstructions: '  - policy: house-style' '    paths: ["."]' > "$dir/agents.yml"
- working-directory: scenario:

### install

- kind: seed
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --repo "$dir" --library "$dir/lib"
- working-directory: scenario:

### landed

- kind: verify
- run: test -d "$dir"
- working-directory: scenario:
