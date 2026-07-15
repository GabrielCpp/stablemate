---
name: stablemate-farrier-setup
description: "Farrier setup guide — install, configure library, write agents.yml, scaffold new services with `farrier scaffold`, bind skills to local CLAUDE.md files via localInstructions."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/stablemate-farrier-setup/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-farrier-setup/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Farrier Setup

Use this skill when setting up farrier in a new repository or adding/modifying
`agents.yml` configuration.

## What Farrier Does

Farrier renders a shared prompt library (the `vigilant-octo/agents` tree) into
per-repo adapter files for Claude (`.claude/skills/`, `.claude/commands/`,
local `CLAUDE.md`), Codex, and Copilot, plus workflow bundles under
`.agents/workflows/` and an `agents.mk` Makefile include.

## Installation

```bash
pipx install farrier
```

Requires Python >= 3.12.

## One-Time Library Configuration

Point farrier at the shared library (only needed once per machine):

```bash
farrier config set-library /path/to/vigilant-octo/agents
```

Verify with:

```bash
farrier config show
```

The config lives at the platform config dir: `~/.config/farrier/config.toml`
(Linux), `~/Library/Application Support/farrier/config.toml` (macOS).

## Repository Setup

Create `agents.yml` at the repository root (default path `<repo>/agents.yml`;
override with `farrier --config <path>`):

```yaml
agents:
  claude: true               # generate .claude/ outputs
  codex: false
  copilot: false

packs:
  - <pack-name>              # bundles from agents/packs/*.yml

# Optional — the install prefix defaults to the repo directory name.
repo:
  name: <repo-name>          # or `prefix:` to set the prefix explicitly
```

Packs are for bundles reused by ≥2 repos; a repo's own overlays and one-off
selections go directly under top-level `skills:` / `prompts:` / `workflows:`
keys (see `agents/packs/CLAUDE.md`). The full key reference (template values,
`workspace:`, `workflow:` runtime config, `exclude:`, `scaffolds:`) lives in
the farrier repo: `docs/features/farrier/agents-yml-config.md` and
`agents.example.yml`.

## Scaffolding a New Service or Repo

When starting a repo (or adding a service folder) from scratch, seed its files
from the library's scaffold definitions instead of hand-writing them.

A scaffold exists to get you moving faster — it seeds structure and
boilerplate, **not** final content. After scaffolding, immediately fill the
tree with the real thing: write the actual service code into the seeded
folders and flesh out seeded docs (`docs/roadmaps/`, `docs/epics/`, …) as the
work produces them. A
scaffolded directory left empty, or a seeded file left as boilerplate, is
unfinished work — not a deliverable.

```bash
# List the scaffolds available to this repo, with their params and defaults
farrier scaffold

# Apply one — placement is a param, never baked into the library
farrier scaffold go-service --param dir=api
farrier scaffold shared-docs                 # standard docs/ hierarchy
farrier scaffold flutter-app --param dir=mobile
```

How it works:

- Scaffold definitions live in the library's `scaffolds/*.yml`; each id
  declares `params` (with defaults; a `~` default means required) and a `tree`
  of files (inline content, `{url: ...}` downloads, bare/null keys for empty
  directories, `$param` placeholders in paths and content).
- The `scaffolds:` list in `agents.yml` — unioned with the ids contributed by
  the selected packs (the `go` pack ships `go-service`, `flutter` ships
  `flutter-app`, `pulumi` ships `pulumi-infra`, `react-router` ships
  `react-router-web`, `shared-docs` ships `shared-docs`) — is the catalog of
  ids the repo may use. With no `agents.yml` yet (bootstrapping), every
  library scaffold is available.
- Every scaffolded file is a **seed**: an existing file is never overwritten,
  so re-running is always safe, and the repo owns the files afterwards (they
  are invisible to `farrier --check`).

Scaffold before wiring `localInstructions` at a new directory — the install
errors if a `localInstructions` path does not exist yet.

## Skill Naming Convention

The installed skill name is the prefix (`repo.prefix`, else `repo.name`, else
the repo directory name) prepended to the skill's library name. Library names
already carry a unique domain prefix (`go-*`, `process-*`, `stablemate-*`,
`acme-*`), and farrier does not double a prefix the name already starts
with — a skill named `acme-auth` installed into the `acme` repo stays
`acme-auth`.

```
library/skills/process/process-story-docs/SKILL.md
  → installed as: <prefix>-process-story-docs
```

So for a repo named `vigilant-octo` using the `product-planning` pack:
- `process/process-story-docs` → `vigilant-octo-process-story-docs`
- `process/process-write-epics-and-stories` → `vigilant-octo-process-write-epics-and-stories`

## localInstructions — Binding Skills to Directories

`localInstructions` renders a skill as a `CLAUDE.md` file inside a target
directory. Claude auto-loads it when working on files in that directory.

```yaml
localInstructions:
  # Single skill → single directory
  - skill: <installed-skill-name>
    paths:
      - path/to/dir

  # Single skill → multiple directories
  - skill: <installed-skill-name>
    paths:
      - dir-a
      - dir-b

  # Multiple skills → one file (aggregated with --- separators)
  - skills:
      - <skill-a>
      - <skill-b>
    paths:
      - path/to/dir

  # Control README.md folding
  - skill: <installed-skill-name>
    paths:
      - "."
    includeReadme: import    # inline (default) | import | none
```

The `skill` value must be the **installed** name (with prefix), not the
library source path. Run farrier once without `localInstructions` and check
`.claude/skills/` to discover the installed names.

Each generated `CLAUDE.md` starts with a `DO NOT EDIT` HTML comment naming
its library source(s), the regeneration command, and a copy-pasteable
`farrier source <path>` command that prints this machine's editable source
paths (one per line for aggregated files). Claude strips block-level HTML
comments before loading the file into context, but anyone opening the file
to edit it sees the banner — follow it to the library source instead of
editing the generated file. (Codex `AGENTS.md`/`CODEX.md` outputs carry no
banner: Codex does not strip HTML comments, so it would leak into the
agent's context.)

## Running Farrier

```bash
# Install/regenerate all outputs
farrier --repo /path/to/repo

# Check for drift without writing (CI use)
farrier --repo /path/to/repo --check

# Override library location for this run
farrier --repo /path/to/repo --library /path/to/vigilant-octo/agents
```

The generated `agents.mk` exposes the same operations as Makefile targets:
`make agent-install` and `make agent-check`.

To trace any generated file back to its editable source, run
`farrier source <generated-file>` and it prints the absolute editable
path(s) on this machine. Skills/commands resolve via their `metadata.source`
front matter; local `CLAUDE.md` files resolve via the repo's live
`agents.yml → localInstructions` mapping (the file's banner is only a
generation-time snapshot, used as fallback when no `agents.yml` is found).
If `agents.yml` no longer maps the file, the command reports it as stale
instead — regenerate to remove it rather than editing it.

## Available Packs

The pack list lives in `agents/packs/*.yml`; each pack's `description:` field
is the source of truth. Current packs:

| Pack | Contents |
|------|----------|
| `agent-library` | library maintenance skill + update-skill prompt (includes `stablemate`) |
| `stablemate` | toolchain skills — coder-workflow, code-review, workhorse-scripting, farrier-setup, ostler, groom |
| `product-planning` | story-docs + write-epics-and-stories skills, product-planning prompts |
| `shared-lifecycle` | planning, review, validation prompts |
| `shared-docs` | docs/misc prompts + standard `docs/` scaffold |
| `qa` | shared QA planning prompts (per-stack QA skills ship with stack packs) |
| `go` | Go backend skills + fix prompts |
| `flutter` | Flutter app skills + prompts (pair with `ui`) |
| `react-router` | React Router web app skills (pair with `ui`) |
| `react-native` | React Native app skills |
| `python-workflow` | Python CLI, testing, workhorse workflow scripting skills |
| `pulumi` | Pulumi infrastructure skills (pair with `infra`) |
| `infra` | GCP CI/IAM conventions, dev-stack hardening, CLI anti-hang rules |
| `ui` | accessibility contract, design-system methodology, Superdesign workflow |
| `research` | autonomous researcher skills, gate-loop prompts, generic research workflow |

## Typical Setup Sequence

1. Install farrier: `pipx install farrier`
2. Set library: `farrier config set-library /path/to/vigilant-octo/agents`
3. Create `agents.yml` at repo root with `agents`, `packs` (and `repo.name` if
   the directory name is not the prefix you want)
4. Seed the repo layout: `farrier scaffold` to list what's available, then
   e.g. `farrier scaffold shared-docs` and `farrier scaffold go-service
   --param dir=api` for each service folder
5. Run `farrier --repo .` to discover installed skill names
6. Add `localInstructions` referencing the installed skill names
7. Run `farrier --repo .` again to generate local `CLAUDE.md` files
8. Commit the generated files

## Troubleshooting

- **"Unknown selected skill reference"** — the skill name in `localInstructions`
  doesn't match an installed skill. Run without `localInstructions` first,
  check `.claude/skills/` for the actual names.
- **Missing output** — verify the pack that carries the skill is listed in `packs:`.
- **Library not found** — run `farrier config show` to check the path, or pass
  `--library` explicitly.
- **`Missing config: .../agents.yml`** — the config file must be named
  `agents.yml` (no leading dot) at the repo root, or passed via `--config`.
