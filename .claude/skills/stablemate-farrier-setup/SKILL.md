---
name: stablemate-farrier-setup
description: "Farrier setup guide — install, configure library, write .agents.yml, bind skills to local CLAUDE.md files via localInstructions."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/farrier-setup/SKILL.md
  do_not_edit: "edit the source in the central prompt library and re-run `make agent-install` to regenerate"
---

# Farrier Setup

Use this skill when setting up farrier in a new repository or adding/modifying
`.agents.yml` configuration.

## What Farrier Does

Farrier renders a shared prompt library (the `vigilant-octo/agents` tree) into
per-repo adapter files for Claude (`.claude/skills/`, `.claude/commands/`,
local `CLAUDE.md`), Codex, and Copilot.

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

The config lives at `~/Library/Application Support/farrier/config.toml` (macOS).

## Repository Setup

Create `.agents.yml` at the repository root:

```yaml
repo:
  name: <repo-name>          # used as install prefix for skill names

agents:
  claude: true               # generate .claude/ outputs
  codex: false
  copilot: false

packs:
  - <pack-name>              # bundles from agents/packs/*.yml
```

## Skill Naming Convention

The installed skill name combines the **namespace** (directory under
`library/skills/`) with the **skill folder name**, joined by a hyphen. The
repo `name` from `.agents.yml` replaces the namespace when the pack is
repo-specific.

For generic/shared packs (e.g. `product-planning`), the installed name uses
the repo name as prefix:

```
library/skills/planning/story-docs/SKILL.md
  → installed as: <repo-name>-story-docs
```

So for a repo named `vigilant-octo` using the `product-planning` pack:
- `planning/story-docs` → `vigilant-octo-story-docs`
- `planning/write-epics-and-stories` → `vigilant-octo-write-epics-and-stories`

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
    includeReadme: import    # inline | import | none
```

The `skill` value must be the **installed** name (with prefix), not the
library source path. Run farrier once without `localInstructions` and check
`.claude/skills/` to discover the installed names.

## Running Farrier

```bash
# Install/regenerate all outputs
farrier --repo /path/to/repo

# Check for drift without writing (CI use)
farrier --repo /path/to/repo --check

# Override library location for this run
farrier --repo /path/to/repo --library /path/to/vigilant-octo/agents
```

## Available Packs

List packs by examining `agents/packs/*.yml`. Common ones:

| Pack | Contents |
|------|----------|
| `product-planning` | story-docs + write-epics-and-stories skills, product-planning prompts |
| `shared-lifecycle` | planning, review, testing prompts |
| `qa` | QA planning prompts and generic QA skill |
| `shared-docs` | scaffolds standard `docs/` layout |
| `story-coder` | autonomous story workflow |
| `go` | Go backend skills |
| `flutter` | Flutter app skills |
| `olympus` | Olympus-specific skills and prompts |

## Typical Setup Sequence

1. Install farrier: `pipx install farrier`
2. Set library: `farrier config set-library /path/to/vigilant-octo/agents`
3. Create `.agents.yml` at repo root with `repo.name`, `agents`, `packs`
4. Run `farrier --repo .` to discover installed skill names
5. Add `localInstructions` referencing the installed skill names
6. Run `farrier --repo .` again to generate local `CLAUDE.md` files
7. Commit the generated files

## Troubleshooting

- **"Unknown selected skill reference"** — the skill name in `localInstructions`
  doesn't match an installed skill. Run without `localInstructions` first,
  check `.claude/skills/` for the actual names.
- **Missing output** — verify the pack that carries the skill is listed in `packs:`.
- **Library not found** — run `farrier config show` to check the path, or pass
  `--library` explicitly.
