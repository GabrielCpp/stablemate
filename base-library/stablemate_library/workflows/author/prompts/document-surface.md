---
agent: agent
---

# Document the surface (OKF UI profile — design time)

The story is authored and approved. If it introduces or reshapes a **user-facing surface**
(a screen, CLI, or server and its elements/behaviors), a **concept**, or a **journey**, update
the OKF **book** now — at design time, from the story's intent — so the coder inherits the
target spec, not a blank page. This is Playbook A (from a description): author the full contract
you can know from intent, and leave only `code:` / `verify:` as **stubs**, because no code exists
yet.

Load the skill and follow it: {{ skill_load_ref("stablemate-okf-modeling", skill_dir() + "/stablemate-okf-modeling/SKILL.md") }}
Use its **"from a high-level description"** playbook. The type vocabulary, the per-type
spec-completeness bar, folder layout, and linter rules live in the `stablemate-ostler` skill it
links to.

Three rules (profile §2/§8) govern this:
- **The book, not a changelog.** OKF is the full, current spec. Your story is a **delta** —
  **merge** it into the affected nodes so they read as the complete new reality; never append
  "this story adds X".
- **Spec-complete to intent.** Enumerate **every** element the story implies (each screen and its
  buttons/dropdowns/inputs, each command/flag, each endpoint) and give each its contract as far as
  the description fixes it — fields/props with type/required/default, `does:` effects, `when:`
  guards, and the **journeys** it enables (`flow` nodes with ordered `steps:`). Only `code:` /
  `verify:` stay stubs.
- **Spec, not implementation.** Say *what*, never *how* — coding patterns belong in the stack
  skills, not the book.

## Inputs

- Epic: `{{ workhorse_var('epic') }}`
- Story path: `{{ workhorse_var('story_path') }}`
- Story dir: `{{ workhorse_var('story_dir') }}`
- Story slug: `{{ workhorse_var('story_slug') }}`
- Features root: `{{ workhorse_var('features_root') }}`
- Mockup dir: `{{ workhorse_var('mockup_dir') }}`

## Steps

1. **Read the story** (`story_path`) and any mockup under `mockup_dir`. Decide whether it
   describes a documentable surface/element/behavior/concept/flow/format.
2. **If it does not** (pure backend/planning story, no surface), output
   `{"doc_status": "skipped"}` and stop. Do not invent nodes.
3. **Otherwise model it to the bar.** Scaffold breadth-first (concepts and shared components
   first so links resolve), **enumerating every element the story implies** — each screen's
   buttons/dropdowns/inputs, each command and flag, each endpoint — plus the **journeys** it
   enables (`flow` nodes). Merge into any node that already exists (the book, not a changelog).
   Author the contract you can know from intent — fields/props with `type`/`required`/`default`,
   `does:` effects, `when:` guards, and relation links (`on:`/`parent:`/`extends:`), with each
   node's key relations in its opening prose. **Leave only `code:` / `verify:` as stubs** — the
   coder grounds them when the code lands.
4. **Converge:** `ostler fmt <the docs you touched>` then `ostler doctor`. Because
   `code:` / `verify:` are not link-checked, an intent-only graph is fully green. Fix any
   error by its named remedy until green for the nodes you touched.

Fail soft: if ostler is unavailable or the repo doesn't use the profile, output
`{"doc_status": "skipped"}` — never block the author run.

## Output

Output JSON only:

```json
{"doc_status": "documented"}
```

`doc_status` is one of `documented`, `skipped`, or `partial` (docs updated but an unrelated
pre-existing `doctor` error remains).
