---
type: fixture
slug: installed-commit-check-repo
title: Installed commit check repo
---
# Installed commit check repo

The commit check repo after `farrier install`, with an untracked `notes.txt` beside it.

- args: dir
- lifetime: scenario

## Steps

### clear

- kind: seed
- run: rm -rf "$dir" && mkdir -p "$dir/home" && printf 'config_version = 2\n' > "$dir/config.toml"

### library-skill

- kind: seed
- run: mkdir -p "$dir/lib/packs" "$dir/lib/library/skills/demo/checked/scripts" && printf '%s\n' --- 'name: checked' 'description: "A skill with a commit check."' 'commit_checks:' '  - run: scripts/check.py' '    budget: 1.5' --- '' 'Check it.' > "$dir/lib/library/skills/demo/checked/SKILL.md" && printf '%s\n' "print('ok')" > "$dir/lib/library/skills/demo/checked/scripts/check.py"

### library-policy

- kind: seed
- run: mkdir -p "$dir/lib/library/policies/git/guarded/scripts" && printf '%s\n' --- 'name: guarded' 'description: "A policy with a commit check."' 'commit_checks:' '  - run: scripts/gate.py' '    budget: 2' --- '' 'Run the gate.' > "$dir/lib/library/policies/git/guarded/POLICY.md" && printf '%s\n' "print('ok')" > "$dir/lib/library/policies/git/guarded/scripts/gate.py"

### agents-yml

- kind: seed
- run: mkdir -p "$dir/docs" && printf '%s\n' agents: '  claude: true' repo: '  name: acme' skills: '  - demo/checked' localInstructions: '  - policies: [guarded]' '    paths: ["."]' '    includeReadme: false' '  - policies: [guarded]' '    paths: ["docs"]' '    includeReadme: false' > "$dir/agents.yml"

### notes

- kind: seed
- run: printf '%s\n' one > "$dir/notes.txt" && printf '%s\n' home/ lib/ config.toml > "$dir/.gitignore"

### install

- kind: seed
- run: HOME="$PWD/$dir/home" STABLEMATE_CONFIG="$PWD/$dir/config.toml" STABLEMATE_FETCH_BASE=0 farrier install --repo "$dir" --library "$dir/lib" > /dev/null

### landed

- kind: verify
- run: test -d "$dir"
