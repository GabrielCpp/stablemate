# The agent library layout

farrier renders an **agent library** into a repository. This document describes
how that library directory is laid out — what each folder holds, the file format
expected, and how names flow from source files to generated adapters. It is the
companion to [`agents.example.yml`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/agents.example.yml),
which documents the consumer-side `agents.yml` that *selects* from this library.

The library is a separate, self-contained directory (the reference one lives in a
private repo; you point farrier at it with `farrier config set-library <dir>`).
farrier never bundles content — it only renders whatever library it is aimed at.

## Top-level layout

```
<library>/                     # the directory passed to `farrier config set-library`
  library/
    skills/<group>/<name>/SKILL.md   # skills — frontmatter + markdown
    prompts/<group>/<name>.md        # prompts — optional frontmatter + markdown
  packs/<pack>.yml             # named bundles a repo opts into via `agents.yml`
  scaffolds/<group>/...        # literal seed files copied into the repo
  workflows/<workflow>/        # workhorse workflow.yaml + prompts + scripts
```

Only `library/` and `packs/` are required for farrier to recognise a directory as
a library — if either is missing, farrier exits with a setup hint. `scaffolds/`
and `workflows/` are optional and only consulted when a selected pack references
them.

## `library/skills/` — skills

A **skill** is a reusable instruction set that an agent loads when working on
matching files. Each skill is a directory containing a `SKILL.md`:

```
library/skills/go/go-testing/SKILL.md
              ^^  ^^^^^^^^^^
              |   skill name  → public id `go-testing`
              group (namespace)
```

- **Name** comes from the *directory* holding `SKILL.md` (`go-testing`), not the
  filename. The parent `group` (`go`) is a namespace used by packs to glob-select
  (`go/*`) but is **stripped** from the generated name.
- A flat `library/skills/<group>/<name>.md` file is also accepted for backwards
  compatibility, but the `<name>/SKILL.md` directory form is the current format
  (it lets a skill keep sibling resource files alongside it).

### Skill file format

```markdown
---
name: go-testing
description: "Go testing patterns. Applies to api/**_test.go."
applyTo: api/**_test.go
---

# Go Testing

Body markdown — the actual instructions…
```

- `name` — the skill's logical name.
- `description` — one-line summary; surfaces in adapter indexes.
- `applyTo` — comma-separated file globs that trigger auto-loading of the skill.
  Keep this accurate; it is what scopes the skill to the right files.
- The body is rendered through Jinja2 (see *Templating* below).

### Generated outputs (per enabled agent)

| Agent   | Skill output path                         |
| ------- | ----------------------------------------- |
| claude  | `.claude/skills/<prefix>-<name>/SKILL.md` |
| codex   | `.agents/skills/<prefix>-<name>/SKILL.md` |
| copilot | `.github/skills/<prefix>-<name>/SKILL.md` |

`<prefix>` is the repo's install prefix (`repo.name`/`repo.prefix` in
`agents.yml`). A skill whose name already equals or starts with the prefix is
not double-prefixed.

## `library/prompts/` — prompts

A **prompt** is an on-demand instruction (a slash-command / one-shot task) rather
than an always-loaded rule. Prompts are flat files under a group:

```
library/prompts/review/self-review.prompt.md   → public id `self-review`
library/prompts/planning/plan-story.md          → public id `plan-story`
```

- Either `.prompt.md` or plain `.md` is accepted; the suffix is stripped for the
  name. The leading group (`review`, `planning`) is the namespace packs glob over
  (`review/*`) and is dropped from the generated name.
- Optional frontmatter selects the executing agent:

  ```markdown
  ---
  agent: agent
  ---
  # Pull Request Self-Review Prompt
  …
  ```

### Generated outputs

| Agent   | Prompt output path                          |
| ------- | ------------------------------------------- |
| claude  | `.claude/commands/<prefix>-<name>.md`       |
| codex   | `.agents/prompts/<prefix>-<name>.prompt.md` |
| copilot | `.github/prompts/<prefix>-<name>.prompt.md` |

## Repo-root instructions (`localInstructions`)

There is **no `library/roots/` skills tree** in the reference library. The normal
way to produce an always-loaded repo-root `CLAUDE.md` / `AGENTS.md` is the
`localInstructions` block in the consumer's `agents.yml`, which promotes an
ordinary installed skill into a directory-local instruction file — use
`paths: ["."]` for the repo root. That is a selection-side feature, documented in
[`agents.example.yml`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/agents.example.yml).

A separate, legacy `roots:` pack key also exists: it reads **flat** files at
`library/roots/<name>.md` (note: flat `.md`, not `<name>/SKILL.md`) and renders
them **only for the copilot agent**, into `.github/copilot-instructions.md`. The
reference library ships no `library/roots/` directory, so this key is effectively
unused — prefer `localInstructions` for repo-root context.

## `packs/<pack>.yml` — bundles

A repo never selects individual skills/prompts — it selects **packs**. A pack is
a YAML manifest listing what it contributes:

```yaml
description: Generic Go repository skills and maintenance prompts.
skills:
  - go/*                 # glob over the skill namespace
prompts:
  - go/*
scaffolds:
  - go/**                # literal seed files
workflows:
  - coder                # a workflows/ directory
includes:
  - shared-lifecycle     # compose other packs (merged, cycle-checked)
```

A pack may also carry a `roots:` list, but it is the legacy copilot-only key
described above (flat `library/roots/<name>.md`); repo-root context normally comes
from the consumer's `localInstructions`, not a pack.

- Every key is a list of patterns matched (case-insensitively, via `fnmatch`)
  against source ids, public ids, and relative paths — so `go/*`, `go-testing`,
  and `skills/go/go-testing` all resolve.
- `includes:` composes packs; sets union and a later pack's scaffold dest-mapping
  overrides an earlier one. Include cycles are detected and rejected.
- Packs selected in `agents.yml` are merged before rendering; nothing in the
  library is installed unless some selected pack pulls it in.

## `scaffolds/` — literal seed files

Scaffolds are copied **verbatim** (not name-mangled like skills/prompts) into the
repo. The output path mirrors the source with its leading namespace segment
stripped, e.g. `scaffolds/shared/docs/README.md` → `docs/README.md`.

Because service-folder names are project-specific, a pack/`agents.yml` may use
the `{src-prefix: dest-dir}` mapping form to retarget a folder-agnostic scaffold
(e.g. point `scaffolds/flutter/.gitignore` at the repo's actual `app/` folder).
Per-service `.gitignore` seeds are written once and then owned by the repo (never
overwritten, exempt from `--check`).

## `workflows/<name>/` — workhorse workflows

Each workflow is a directory consumed by
[`workhorse-agent`](https://pypi.org/project/workhorse-agent/):

```
workflows/coder/
  workflow.yaml     # the workflow graph (see workhorse docs/WORKFLOW.md)
  prompts/          # prompts the workflow steps invoke
  scripts/          # helper scripts the workflow shells out to
  docs/
```

A pack opts into a workflow with `workflows: [coder]`. farrier copies the
workflow tree into `.agents/workflows/<name>/` and auto-pulls any skills/prompts
the workflow's prompts reference via `instruction_ref("…")` / `prompt_ref("…")`,
so a workflow's dependencies install even if a pack lists only the workflow.

## Templating

Skill and prompt bodies are rendered through **Jinja2** before output:

- `{{ template.<key> }}` — substitutes values from the `agents.yml` `template:`
  block. Always give shared library files a `| default("…")` fallback so they
  remain installable without that key.
- `{{ instruction_file("<name>") }}` / `instruction_ref` / `prompt_ref` — cross-
  link sibling skills and prompts instead of duplicating their content.
- Undefined values resolve leniently (they do not hard-fail the render), but
  prefer explicit defaults for anything a consumer is expected to override.

## How a source file becomes a generated name

1. **id** — derived from the source path: for `…/<name>/SKILL.md` the parent
   directory; for a flat file its stem with a known suffix stripped. Group
   segments are namespaces used only for pack globbing.
2. **public id** — the last path segment, kebab-cased (`Go Testing` → `go-testing`).
3. **public name** — `<prefix>-<public-id>`, unless the id already equals or
   starts with the prefix (avoids `myrepo-myrepo-db`).

This is why a pack can select with a coarse glob (`go/*`) while the generated
artifacts land under the consuming repo's own prefix.
