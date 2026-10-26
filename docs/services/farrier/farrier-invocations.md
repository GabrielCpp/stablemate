---
type: fragment
slug: farrier-invocations
title: 'farrier — render the agent prompt library into a repository: Invocations'
---
# farrier — render the agent prompt library into a repository: Invocations

- host: [farrier — render the agent prompt library into a repository](farrier.md)

Each invocation below is one command line that a [flow](entries.md) step performs.

## Invocations

### write-starter-config

- on: [init](farrier-commands-init.md#init)
- trigger: an operator runs `farrier init` in a directory with no agents.yml
- fixture: empty-dir dir=c200
- does:
  - Writes a starter `agents.yml` into the repository.
- run: invoke(argv=["init", "--repo", "c200"], env={"HOME": "c200/home", "STABLEMATE_CONFIG": "c200/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c200/pipx-stub-bin:$PATH"})
- verify: created(subject="c200/agents.yml")

### render-selected-adapters

- on: [install](farrier-commands-install.md#install)
- trigger: an operator runs `farrier install` in a configured repository
- fixture: demo-skill-repo dir=c201
- does:
  - Renders the selected skill files into the repository.
- run: invoke(argv=["install", "--repo", "c201", "--library", "c201/lib"], env={"HOME": "c201/home", "STABLEMATE_CONFIG": "c201/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c201/pipx-stub-bin:$PATH"})
- verify: created(subject="c201/.claude/skills/acme-demo/SKILL.md")

### check-for-drift

- on: [install](farrier-commands-install.md#install)
- trigger: an operator runs `farrier install --check`
- fixture: demo-skill-repo dir=c202
- does:
  - Reports an expected output that is absent from the working tree.
- run: invoke(argv=["install", "--check", "--repo", "c202", "--library", "c202/lib"], env={"HOME": "c202/home", "STABLEMATE_CONFIG": "c202/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c202/pipx-stub-bin:$PATH"})
- verify: stdout(text="missing: .claude/skills/acme-demo/SKILL.md")

### regenerate-outputs

- on: [install](farrier-commands-install.md#install)
- trigger: an operator re-runs `farrier install` after correcting the library source
- fixture: demo-skill-repo dir=c203
- does:
  - Writes the expected outputs back into the repository.
- run: invoke(argv=["install", "--repo", "c203", "--library", "c203/lib"], env={"HOME": "c203/home", "STABLEMATE_CONFIG": "c203/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c203/pipx-stub-bin:$PATH"})
- verify: created(subject="c203/.claude/skills/acme-demo/SKILL.md")

### install-the-user-library

- on: [install---user](farrier-commands-install.md#install---user)
- trigger: an operator runs `farrier install --user`
- fixture: user-library-home dir=c204
- does:
  - Writes the selected skills into the harness home directory.
- run: invoke(argv=["install", "--user", "--home", "c204/home", "--library", "c204/lib"], env={"HOME": "c204/home", "STABLEMATE_CONFIG": "c204/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c204/pipx-stub-bin:$PATH"})
- verify: created(subject="c204/home/.claude/skills/demo/SKILL.md")

### list-the-layer-stack

- on: [library](farrier-commands-init.md#library)
- trigger: an operator runs `farrier library list`
- fixture: overlay-over-base dir=c205
- does:
  - Lists the layers of the resolved library stack.
- run: invoke(argv=["library", "list", "--skills"], env={"HOME": "c205/home", "STABLEMATE_CONFIG": "c205/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c205/pipx-stub-bin:$PATH"})
- verify: stdout(text="# layer: ")

### resolve-a-generated-file

- on: [source](farrier-commands-init.md#source)
- trigger: an operator runs `farrier source` on a generated file
- fixture: generated-demo-skill dir=c206
- does:
  - Prints the library file the generated file came from.
- run: invoke(argv=["source", "c206/.claude/skills/acme-demo/SKILL.md", "--library", "c206/library-dir"], env={"HOME": "c206/home", "STABLEMATE_CONFIG": "c206/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c206/pipx-stub-bin:$PATH"})
- verify: stdout(text="library/skills/demo/SKILL.md")

### apply-a-scaffold

- on: [scaffold](farrier-commands-init.md#scaffold)
- trigger: an operator runs `farrier scaffold` with a scaffold id
- fixture: scaffold-library dir=c207
- does:
  - Writes the scaffold files that the repository lacks.
- run: invoke(argv=["scaffold", "service-gitignore", "--library", "c207/scaffold-library", "--repo", "c207"], env={"HOME": "c207/home", "STABLEMATE_CONFIG": "c207/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c207/pipx-stub-bin:$PATH"})
- verify: created(subject="c207/api/.gitignore")

### print-the-version

- on: [version](farrier-commands-init.md#version)
- trigger: an operator runs `farrier version`
- fixture: none, because the version comes from the installed package metadata
- does:
  - Prints the installed farrier version.
- run: invoke(argv=["version"])
- verify: stdout(matches="^[0-9]+\\.[0-9]+\\.[0-9]+")

### record-the-library

- on: [config](farrier-commands-init.md#config)
- trigger: an operator runs `farrier config set-library`
- fixture: library-dir-with-packs dir=c208
- does:
  - Records the library directory in the shared config file.
- run: invoke(argv=["config", "--config", "c208/c.toml", "set-library", "c208/lib"], env={"HOME": "c208/home", "STABLEMATE_CONFIG": "c208/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c208/pipx-stub-bin:$PATH"})
- verify: contents(subject="c208/c.toml", text="library_dir")

### eject-a-skill

- on: [eject](farrier-commands-init.md#eject)
- trigger: an operator runs `farrier eject` on a generated skill folder
- fixture: own-skill-repo dir=c905
- does:
  - Strips farrier's provenance from the skill folder and unselects it in `agents.yml`.
- run: invoke(argv=["eject", "acme-demo", "--repo", "c905", "--library", "c905/lib"], env={"HOME": "c905/home", "STABLEMATE_CONFIG": "c905/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c905/pipx-stub-bin:$PATH"})
- verify: omits(subject="c905/.claude/skills/acme-demo/SKILL.md", text="generated_by")

### diagnose-the-repository

- on: [doctor](farrier-commands-workflows.md#doctor)
- trigger: an operator runs `farrier doctor`
- fixture: bare-agents-yml dir=c209
- does:
  - Prints a warning for each gap in the repository configuration.
- run: invoke(argv=["doctor", "--repo", "c209"], env={"HOME": "c209/home", "STABLEMATE_CONFIG": "c209/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c209/pipx-stub-bin:$PATH"})
- verify: stdout(text="warning: ")

### list-installed-workflows

- on: [workflows](farrier-commands-workflows.md#workflows)
- trigger: an operator runs `farrier workflows`
- fixture: pipx-two-workflows dir=c210
- does:
  - Lists each installed workflow under its provider.
- run: invoke(argv=["workflows"], env={"HOME": "c210/home", "STABLEMATE_CONFIG": "c210/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c210/pipx-stub-bin:$PATH"})
- verify: stdout(text="    planner")

### wire-the-hook-manager

- on: [hooks](farrier-commands-workflows.md#hooks)
- trigger: an operator runs `farrier hooks install`
- fixture: husky-repo dir=c211
- does:
  - Writes the fenced hook entry into the hook manager file.
- run: invoke(argv=["hooks", "install", "--repo", "c211"], env={"HOME": "c211/home", "STABLEMATE_CONFIG": "c211/config.toml", "STABLEMATE_FETCH_BASE": "0", "PATH": "c211/pipx-stub-bin:$PATH"})
- verify: contents(subject="c211/.husky/pre-commit", text="make farrier-run-hook")
