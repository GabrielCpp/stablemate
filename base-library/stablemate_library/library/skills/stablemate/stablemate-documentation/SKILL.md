---
name: stablemate-documentation
description: "How to record or refresh a story's documentation in docs/features/** as OKF Concepts via ostler — the scaffold→author→fmt→doctor loop for the UI-profile node types (screen/component/interaction/cli/command/server/endpoint/invocation/flow/concept/format) and for plain prose features, plus the ostler-owns-structure / you-author-prose rule. Load whenever an agent finishes a story that changes user-facing behavior, a surface, a command, an endpoint, or architecture and needs to write or update its docs."
---

# Documentation (per-story docs via ostler OKF)

Load this skill when you have finished a **story** (or any change to user-facing behavior,
architecture, a surface, a command, or an endpoint) and need to **write or refresh its
documentation** under `docs/features/`. It is the action-oriented companion to [[ostler]] (the
full CLI reference) for the narrow, common job of "I did the work, now record it." To model a
*whole app's* surface graph from scratch or by reading existing code, load [[okf-modeling]]
instead; this skill is the incremental, one-story update.

The golden rule: **`docs/` is a knowledge graph, not a folder of loose markdown.** Every doc is
an OKF (Open Knowledge Format) **Concept** — one `.md` file with YAML frontmatter (hard
requirement: a non-empty `type`) plus a markdown body, its identity being its path under `docs/`.
**ostler owns the structure and ids; you author the prose into the skeleton it scaffolds.** Never
hand-invent frontmatter or a `docs/features/` path yourself — call `ostler` so the file is
conformant and `ostler doctor` stays green.

Three rules govern *what* you write (from `docs/okf-ui-profile.md`):

1. **The book, not a changelog.** The OKF graph is the **full, always-current spec** of the
   system. Your story is a **delta** — so **merge it into the book**: edit the affected nodes so
   they describe the *new current reality* completely. Never write "this story added X"; a reader
   who never saw the story must get the whole, correct spec. (The story stays in `docs/epics/**`;
   you are updating `docs/features/**`.)
2. **Spec-complete — enough to regenerate the code.** A node carries every field with its
   type/default/required, every flag/arg, every effect and guard, the algorithm as ordered steps,
   errors/exit codes, and (for UI) the DOM/props/state contract. A one-line stub is below bar. See
   the per-type checklist in [[ostler]] → "The OKF UI profile" (profile §8).
3. **Spec, not implementation.** Document *what* the code does — the behavior and contract. Do
   **not** write coding patterns, idioms, or library/structure choices; those are owned by the
   stack skills (`go`, `react-router`, `python-testing`, …), not the book. `code:`/`verify:` anchor
   the current implementation; the prose never prescribes a technique.

## Which shape: a UI-profile node, or a plain `feature`?

- **A surface, element, behavior, or concept your story touched → a UI-profile node.** A screen,
  a component, a click/keyboard interaction, a CLI command, an HTTP/WS endpoint, a domain or code
  concept, a multi-step flow, or a file format. These are **structured and machine-navigable**,
  and their conformance is a **hard `ostler doctor` gate**. This is the default for feature work.
  Read the type table, folder layout, and linter rules in [[ostler]] → "The OKF UI profile."
- **A prose-only reference → a plain `feature`.** When the thing is best explained as narrative
  (an architecture overview, a subsystem's why/constraints) with no enumerable surface, use the
  `feature` flow further below.

## The story-documentation loop (UI profile)

The default: **scaffold → author → fmt → doctor.** Never hand-write the file.

1. **Find what already exists** (don't duplicate a node):
   ```bash
   ostler list --type screen --json          # or component/interaction/cli/command/endpoint/concept/…
   ostler search <slug> --json               # ostler trace <id|slug|anchor>
   ```

2. **Scaffold the node ostler doesn't have yet** — this places it in its canonical path/heading
   with conformant frontmatter, the H1, bullet **stubs**, and (for surfaces) the required-section
   skeleton:
   ```bash
   # a file-level surface/concept → docs/features/<service>/<context>/<name>.md
   ostler scaffold screen changes-view --service groom --title "Changes view"
   ostler scaffold concept diff       --service groom --title "Diff"

   # a section-level element/behavior → a `### id` under its typed `## Heading` in an existing doc
   ostler scaffold interaction click-file-opens-diff --in docs/features/groom/gui/screens/changes-view.md
   ostler scaffold command  run --in docs/features/workhorse/workhorse.md
   ```

3. **Author to the spec-complete bar, merging your delta in.** Edit the `.md` directly (the body
   is the sanctioned surface). If the node already exists, **merge** your story's change into it so
   it reads as the complete current spec (rule 1) — don't bolt on a note. Fill the structured
   bullets to the per-type completeness bar (rule 2; each type's bullets are in [[ostler]]):
   fields with `type`/`required`/`default`, flags/args item-by-item, `does:` as ordered effects,
   errors/exit codes, and for UI the `dom:`/`props:`/`states:` contract. Describe behavior, not
   coding patterns (rule 3). Since you just wrote the code, set `code:` / `verify:` to the real
   `path::symbol`:
   ```markdown
   ### click-file-opens-diff
   - on: [changes-file-row](#changes-file-row)
   - trigger: click
   - when: `mode == changes`
   - does:
     - state: mark row `.active`, clear siblings
     - dom: render single-file diff
   - code: `groom/groom/templates/dashboard.html::wireChanges`
   - verify: `groom/tests/test_render.py::test_changes_groups_diffs_per_repo`
   ```

4. **Canonicalize, then gate:**
   ```bash
   ostler fmt docs/features/<service>/…    # frontmatter/bullet/heading shape — never touches prose
   ostler doctor                            # non-zero exit on any error — safe to gate the story on
   ```
   Every doctor error has a mechanical remedy (fmt fixes casing/order; scaffold stubs a missing
   section/bullet; you fix a broken link). `code:` / `verify:` are **not** link-checked here — they
   are code refs grounded at a later QA gate. See the full rule table in [[ostler]].

## Updating an existing UI node

The node already exists → **just edit its body/bullets in place**, then `ostler fmt` + `ostler
doctor`. No scaffold call. To move or rename a node so links follow, use `ostler edit
rename/relink … --write` (dry-run by default). Preserve the frontmatter `type`/`slug` — those are
the graph identity.

## Plain `feature` docs (prose-only)

For a narrative reference with no enumerable surface, use the built-in `feature` type and its
`ostler create feature` flow:

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

## When to reach for the neighbors

- **The type table, folder layout, bullet vocabulary, and full linter rules** for the UI profile →
  [[ostler]] ("The OKF UI profile").
- **Modeling a whole app's surface graph** from scratch (from a description) or from existing code
  → [[okf-modeling]]. This skill is the one-story increment; that one is the bulk build.
- **The wider planning graph** — epics, stories, seeds, knowledge records, `docs/specs/**`
  workflow artifacts, the coverage model, `next-epic`/`next-story` — → [[ostler]].
