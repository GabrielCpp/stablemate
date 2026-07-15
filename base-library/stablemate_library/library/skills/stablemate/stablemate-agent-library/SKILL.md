---
name: stablemate-agent-library
description: "Agent Library Maintenance & Install. Applies to agents.yml,.agents/**,agents/library/**,agents/packs/**,agents/scaffolds/**."
applyTo: agents.yml,.agents/**,agents/library/**,agents/packs/**,agents/scaffolds/**
---

# Agent Library Maintenance & Install

Use this skill when changing the shared agent library (skills, prompts, packs,
scaffolds) **and** when propagating those changes into a consuming repository
with `make agent-install`.

The library's filesystem location is never hardcoded — resolve it with
`farrier config show library_dir` (or `farrier config show` for all keys).
Do not assume it lives at a particular path like `vigilant-octo/agents`; that
is just one possible checkout, and treating it as fixed will conflate a
specific machine's layout with the library itself.

The agent library is the single source of truth. The per-repo `.codex/`,
`.claude/`, `.github/instructions/`, `.github/skills/`, `.github/prompts/`,
`.agents/workflows/`, and local `AGENTS.md`/`CLAUDE.md` files are **generated
outputs** — never hand-edit them. Change the library, then re-install.

## Library layout

```
<library_dir>/               # the prompt-library CONTENT — path from `farrier config show library_dir`
  library/
    skills/<group>/<name>.md   # skill files (YAML frontmatter + markdown)
    prompts/<group>/*.md       # prompt files
    roots/                     # root instruction files (CLAUDE.md / AGENTS.md)
  packs/<pack>.yml      # named bundles of skills + prompts a repo opts into
  scaffolds/*.yml       # scaffold definitions applied via `farrier scaffold <id>`
```

The renderer that turns this content into a repo's adapters is **`farrier`**, a
separate published package (in the public `stablemate` repo) — it is not part of
this content tree. Install it with `pipx install farrier` and point it at this
library once with `farrier config set-library /path/to/agent-library`. Run
`farrier config show` any time to confirm the currently configured `library_dir`.

## Editing the library

Follow the reuse-before-create policy in `library/skills/CLAUDE.md` and
`library/skills/README.md` — check for a generic skill before writing a new one,
and add only project-specific deltas to project groups (never duplicate a generic
skill's rules).

1. **Edit a skill** — change the file under `skills/<group>/<name>.md`. Keep the
   `applyTo` frontmatter accurate; it controls which file globs load the skill.
2. **Add a skill** — create `skills/<group>/<name>.md`, then reference it from a
   pack under `skills:` as `<group>/<name>` (no `.md` extension).
3. **Edit a prompt** — change `prompts/<group>/<name>.md`; packs reference these
   under `prompts:` (globs like `review/*` are allowed).
4. **Wire it into a pack** — a skill or prompt is only installed if a pack the
   repo selects in `agents.yml` includes it. Packs compose via `includes:`.

Cross-link sibling skills with the `{% raw %}{{ instruction_file("<name>") }}{% endraw %}`
template helper (where `<name>` is the target skill's base name) rather than
duplicating content.

## Installing into the working repo

After any library change, regenerate the adapters in **every consuming repo** that
selects the affected pack. From the consuming repo root:

```bash
# Regenerate adapters from the library (writes .claude/, .codex/, .agents/, etc.)
timeout 300 make agent-install

# Verify adapters are current without writing (use in CI / pre-commit)
timeout 120 make agent-check
```

`make agent-install` runs `farrier --repo "$(CURDIR)"`. `AGENTS_DIR` defaults to
`$(shell farrier config show library_dir)` — the location recorded once via
`farrier config set-library` — so the generated Makefile never hardcodes a
path either. If the library lives somewhere else for this invocation, override
the dir explicitly:

```bash
timeout 300 make agent-install AGENTS_DIR=/path/to/agent-library
```

You can also invoke the installer directly, using whatever `farrier config show
library_dir` reports (or an explicit override):

```bash
timeout 300 farrier --repo /path/to/repo --library "$(farrier config show library_dir)"
timeout 120 farrier --repo /path/to/repo --check --library "$(farrier config show library_dir)"
```

## Verification before calling the work done

1. `make agent-check` passes in the consuming repo (no drift).
2. The new/changed skill or prompt appears in the generated `.claude/` (and any
   other enabled adapter) output.
3. `agents.yml` `packs:` actually selects the pack that carries the change —
   otherwise the install is a no-op for that repo.
4. Commit the regenerated adapter files alongside the library change.

Every command above is bounded by a wall-clock `timeout`, per
`{{ instruction_file("infra-cli-writer") }}`.

