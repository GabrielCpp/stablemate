---
name: stablemate-documentation
description: "How to push feature documentation into a repo's docs/ as OKF Concepts via ostler — the create-or-update flow for docs/features/**, what a feature doc should contain, and the ostler-owns-structure / you-author-prose rule. Use whenever an agent finishes work that changes user-facing behavior or architecture and needs to record or refresh a feature's docs."
metadata:
  generated_by: farrier
  source: library/skills/stablemate/documentation/SKILL.md
  do_not_edit: "edit the source in the central prompt library and re-run `make agent-install` to regenerate"
---

# Documentation (feature docs via ostler OKF)

Load this skill when you have built or changed something and need to **write or update its
documentation** under `docs/` — most often a **feature** doc in `docs/features/`. It is the
action-oriented companion to [[ostler]] (the full doc-graph CLI reference): use this for the
narrow, common job of "I did work, now document the feature."

The golden rule: **`docs/` is a knowledge graph, not a folder of loose markdown.** Every doc is
an OKF (Open Knowledge Format) **Concept** — one `.md` file with YAML frontmatter (hard
requirement: a non-empty `type`) plus a markdown body, its identity being its path under `docs/`.
**ostler owns the structure and ids; you author the prose into the skeleton it scaffolds.** Never
hand-invent frontmatter ids or a `docs/features/` path yourself — call `ostler` so the file is
conformant and `ostler doctor` stays green.

## The create-or-update flow

1. **Check whether the feature already exists** (don't create a duplicate):
   ```bash
   ostler list --type feature --json
   ostler search <slug> --type feature --json      # or: ostler trace <slug>
   ```

2. **If it does not exist, scaffold it** — this allocates the id and writes conformant
   frontmatter, so it must go through ostler, not a hand-written file:
   ```bash
   ostler create feature <slug> --title "<Human title>" [--area <area>] [--route <path>]
   ```
   Writes `docs/features/<area>/<slug>.md` (or flat `docs/features/<slug>.md` with no `--area`):
   ```markdown
   ---
   type: feature
   id: <allocated-id>
   slug: <slug>
   title: <Human title>
   area: <area>        # only if --area given
   route: <path>       # only if --route given
   ---
   # <Human title>
   ```
   Use `--json` to capture the allocated `id` (`{"ok": true, "id": "...", ...}`).

3. **Author the body prose by editing the scaffolded `.md` directly.** The body is the
   sanctioned hand-edit surface — ostler does not manage it. Write the real documentation here
   (see "What a feature doc should contain" below).

4. **Validate before you're done:**
   ```bash
   ostler doctor        # non-zero exit on an error-level break — safe to gate on
   ```

## Updating an existing feature

There is **no `ostler set`/update verb for the built-in `feature` type** — that's expected:

- **Refresh the docs → just edit the body prose in place.** This is the normal case and needs no
  ostler call. Re-run `ostler doctor` afterward.
- **Change the frontmatter identity** (title/area/route) → hand-edit the frontmatter keys in
  place, but **preserve `type`, `id`, and `slug`** (those are the graph identity). Do not
  renumber the `id`.
- **Move or rename** (change slug/path so references must follow) → use ostler so links stay
  consistent (dry-run by default; `--write` applies):
  ```bash
  ostler edit rename <old-slug> <new-slug> --write
  ostler edit relink <old-path> <new-path> --write
  ```
- **Re-scaffold from scratch** → `ostler delete feature <slug>` then `ostler create feature …`.

## What a feature doc should contain

Aim for an as-built reference a future agent or human can act on — not a changelog. A good shape
(see `docs/features/groom.md` in `stablemate` for a worked example):

- **Context** — why the feature exists; the problem it solves and the intended outcome.
- **Constraints** — load-bearing rules (stack, security, invariants) that must not be broken.
- **Architecture** — package/module layout, key files and their roles, the main flow.
- **Interfaces** — commands, routes, or APIs it exposes.
- **Non-goals / risks** — what it deliberately does not do; known failure modes.
- **Verification** — how to run it and confirm it works end-to-end.

## Conformance caveat (legacy docs)

Some existing `docs/features/*.md` were authored by hand **without frontmatter** (e.g.
`stablemate`'s `docs/features/groom.md` starts straight at `# groom`). Those are **not** valid OKF
Concepts and will fail `ostler doctor` schema checks. To bring one under management, add the
required `type: feature` / `slug` / `title` frontmatter (matching what `ostler create feature`
would generate) — either by scaffolding a fresh feature and moving the prose in, or via ostler's
one-time migration (`ostler`'s `scripts/okf_migrate.py`). When you touch such a file, prefer
making it conformant over leaving it orphaned from the graph.

## When to reach for [[ostler]] instead

This skill covers feature docs. For the wider graph — epics, stories, seeds, knowledge records,
`docs/specs/**` workflow artifacts, the coverage model, `next-epic`/`next-story`, and the full
`ostler doctor` semantics — load [[ostler]].
