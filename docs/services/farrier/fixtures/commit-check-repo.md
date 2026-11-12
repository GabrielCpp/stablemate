---
type: fixture
slug: commit-check-repo
title: Commit check repo
---
# Commit check repo

A repository whose library gives one selected skill and one selected policy a commit check each. Nothing is installed yet.

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

### landed

- kind: verify
- run: test -d "$dir"
