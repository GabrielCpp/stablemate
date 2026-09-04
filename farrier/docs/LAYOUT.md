# The agent library layout

farrier renders an **agent library** into a repository. This document describes
how that library directory is laid out — what each folder holds, the file format
expected, and how names flow from source files to generated adapters. It is the
companion to [`agents.example.yml`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/agents.example.yml),
which documents the consumer-side `agents.yml` that *selects* from this library.

The library is a self-contained directory. Stablemate's public base library is
discovered automatically; `farrier config set-library <dir>` selects an optional
overlay whose content takes precedence. Farrier never bundles content in its wheel.

## Top-level layout

```
<library>/                     # a base library or optional overlay
  library/
    skills/<group>/<name>/SKILL.md   # skills — frontmatter + markdown
    prompts/<group>/<name>.md        # prompts — optional frontmatter + markdown
    policies/<group>/<name>.md       # policies — aggregated text, never installed
  packs/<pack>.yml             # named bundles a repo opts into via `agents.yml`
  scaffolds/*.yml              # scaffold definitions applied via `farrier scaffold <id>`
```

Only `library/` is required for farrier to recognise a directory as a library — that is
the whole of `farrier._vendor.stablemate_core.layout.is_library_dir`, and a path lacking it gets a setup
hint. `packs/` and `scaffolds/` are optional and only consulted when
something selects from them; the base library, for instance, ships `library/` and
`packs/` and nothing else.

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
- Each skill uses the `<name>/SKILL.md` directory form, allowing references and
  scripts to live beside the instruction file.

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

`<prefix>` is the repo's install prefix: the repository directory's name,
kebab-cased. It is derived, not set in `agents.yml`. A skill whose name already
equals or starts with the prefix is not double-prefixed.

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
- Optional frontmatter selects the executing agent and describes the command:

  ```markdown
  ---
  agent: agent
  description: Review the current PR and fix the comments
  argument-hint: <pr-number>
  ---
  # Pull Request Self-Review Prompt
  …
  ```

  `description` (and the optional `argument-hint`) drive the **Claude slash-command
  header** — see below. `agent` is farrier-internal selection metadata and never
  leaks into a generated command.

### Generated outputs

| Agent   | Prompt output path                          |
| ------- | ------------------------------------------- |
| claude  | `.claude/commands/<prefix>-<name>.md`       |
| codex   | `.agents/prompts/<prefix>-<name>.prompt.md` |
| copilot | `.github/prompts/<prefix>-<name>.prompt.md` |

The **claude** command is emitted with a generated YAML header so the slash command
is discoverable — `claude-code-acp` reads `description` from it to advertise the
command over ACP (without it, the command never appears in Zed's autocomplete). The
header carries the slash-command keys (`description`, `argument-hint`, and `model` /
`allowed-tools` when set) plus the same `metadata:` provenance block generated skills
get (`generated_by` / `source` / `do_not_edit`), and drops farrier-internal keys
(`agent`, `name`). `description` falls back to the body's first `# heading` when the
source sets none. The **codex** and **copilot** prompt files are copied through
verbatim (their own frontmatter intact).

## `library/policies/` — policies

A **policy** is standing repo text that is only ever *aggregated* — into a generated
`AGENTS.md`, through a `localInstructions` mapping. It is never installed as a skill or
a command, never appears under `.claude/skills/`, is never an `instruction_file()`
target, and is never returned by a tag query. Policies are flat files under a group,
like prompts:

```
library/policies/stablemate/stablemate-repo.md   → policy name `stablemate-repo`
```

The reason the kind exists is the double charge. A skill folded into an always-loaded
`AGENTS.md` pays twice: its whole body is resident every turn *and* its `name` plus
`description` sit in the skill index the agent carries every turn — advertising, as
something to load on demand, text that is already above it in the window. For thirty
skills that index is roughly 15 KB. A policy pays the first charge only.

### Policy file format

```markdown
---
name: stablemate-repo
description: House rules for this repository.
---

# stablemate

Body markdown — the actual rules…
```

- `name` and `description` are for humans and for farrier's error messages; neither is
  emitted anywhere, because the front matter is stripped before aggregation.
- No `applyTo` and no `tags`: a policy is not auto-loaded by file glob and is not
  discoverable by query. It applies wherever the `AGENTS.md` that carries it applies.
- The body is rendered through Jinja2, exactly like a skill body (see *Templating*).
- A policy bundles no sibling assets. Text is the whole of it.

### Addressing

A policy is referenced by its **bare basename**, with no repo prefix ever added —
`stablemate-repo`, not `<prefix>-stablemate-repo`. There is nothing installed for a
prefix to disambiguate against. The namespaced form (`stablemate/stablemate-repo`) and
the relative path both resolve too; a name that is ambiguous across two groups is an
error rather than a silent pick.

### Generated outputs

None. That is the invariant: a policy reaches a repository through a `localInstructions`
mapping or not at all, and there is no `policies:` key at the top of `agents.yml` and
none in a pack, because there is no selection state for one to carry.

## Repo-root instructions (`localInstructions`)

There is **no `library/roots/` skills tree** in the reference library. The normal
way to produce an always-loaded repo-root `CLAUDE.md` / `AGENTS.md` is the
`localInstructions` block in the consumer's `agents.yml`, which aggregates library
text into a directory-local instruction file — use `paths: ["."]` for the repo root.
A mapping may name `policies:` (library text that exists only here), `skills:`
(installed skills, promoted), and `prompts:` (installed commands, always loaded); they
are joined in that order, standing rules ahead of procedures, separated by a `---`
rule. Text that only ever belongs to one repo's root file wants to be a **policy** —
see above for why a skill in that position is charged twice. That is a selection-side feature, documented in
[`agents.example.yml`](https://github.com/GabrielCpp/stablemate/blob/main/farrier/agents.example.yml).

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
  - go-service           # scaffold ids from scaffolds/*.yml
includes:
  - shared-lifecycle     # compose other packs (merged, cycle-checked)
```

- Every key is a list of patterns matched (case-insensitively, via `fnmatch`)
  against source ids, public ids, and relative paths — so `go/*`, `go-testing`,
  and `skills/go/go-testing` all resolve.
- `includes:` composes packs; selections union. Include cycles are detected
  and rejected. Scaffold entries are literal ids (no globs).
- Packs selected in `agents.yml` are merged before rendering; nothing in the
  library is installed unless some selected pack pulls it in.

## `scaffolds/` — scaffold definitions

Scaffolds are **not** rendered at install time. Each `scaffolds/*.yml` file maps
scaffold ids to a definition — `description`, `params` (defaults; a `~`/null
default means required), and a `tree` of files (inline string content,
`{url: ...}` downloads, null/`{}` empty directories; `$param` placeholders substitute
in paths and inline content, plus built-ins `$repo_name`/`$repo_title`):

```yaml
go-service:
  description: Seed a Go service folder.
  params:
    dir: api
  tree:
    $dir/.gitignore: |
      bin/
```

A repo applies one with `farrier scaffold <id> --param dir=api`; the ids listed
under `scaffolds:` in its `agents.yml` and its selected packs form the catalog
it may use (every library id when no `agents.yml` exists yet). Because
service-folder names are project-specific, placement is a `--param`, never a
library path. Scaffolded files are seeds: written once, never overwritten, and
invisible to `--check`.

## Workflows are not part of the library

A library ships no workflows, and farrier installs none. A workflow is a Python
distribution built on
[`workhorse-agent`](https://pypi.org/project/workhorse-agent/) that declares its own
command — a distribution's business, installed with `pip`/`uv`, not rendered out of a
library:

```bash
uv tool install workhorse-workflows
workhorse-research run --dry-run # static preflight, drives nothing
workhorse-coder run
```

There is no `workflows:` key in a pack or in `agents.yml`, no `workflows/` directory in
a library, and nothing under `.agents/workflows/`. A leftover `workflows:` list is
ignored rather than rejected. What farrier still generates is the launcher
(`.agents/agents.mk`) and the per-repo context manifest
(`.agents/agents-context*.json`) — the first regenerates and verifies the adapters, the
second is how a running workflow resolves `instruction_ref` against *this* repo's
adapters. Both are emitted for every install, workflow or not.

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
   starts with the prefix (avoids `myrepo-myrepo-db`). Policies stop at step 2: they
   generate no artifact, so there is nothing for a prefix to name.

This is why a pack can select with a coarse glob (`go/*`) while the generated
artifacts land under the consuming repo's own prefix.
