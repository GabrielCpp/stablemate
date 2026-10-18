---
type: fixture
title: Prompt repo
---
# Prompt repo

The demo skill repo with a library prompt `acme/grill` selected under `prompts:`.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- working-directory: scenario:
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-demo

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/skills/demo.md")" && printf '%s\n' --- 'name: demo' 'description: "A skill."' --- '' 'Use it.' > "$dir/lib/library/skills/demo.md"

### agents-yml

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/agents.yml")" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' skills: '  - demo' prompts: '  - acme/grill' > "$dir/agents.yml"

### prompt

- kind: seed
- working-directory: scenario:
- run: mkdir -p "$(dirname "$dir/lib/library/prompts/acme/grill.md")" && printf '%s\n' --- 'description: "A prompt."' --- '' Ask. > "$dir/lib/library/prompts/acme/grill.md"

### landed

- kind: verify
- working-directory: scenario:
- run: test -d "$dir"
