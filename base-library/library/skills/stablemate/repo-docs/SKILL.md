---
name: repo-docs
description: "How to write and maintain a repo's prose entry surface — CLAUDE.md (root and nested), README.md, and <package>/docs/*.md: the admission test that decides what earns a slot in every-turn agent context, the root/nested/skill/README/docs placement table, why `@`-imports are not splitting, and the README-outgrew-itself refactor (extract whole sections into <package>/docs/<TOPIC>.md, leave a summary plus an absolute link). Load when creating or editing a CLAUDE.md or README.md, when adding a rule an agent keeps getting wrong, when a file has outgrown its budget, or when a change makes an existing instruction stale. Not for docs/features/** — that is ostler's OKF graph."
tags: [standards, docs]
---

# Repo docs (CLAUDE.md, README.md, and the docs/ folder)

Load this skill when you are writing or maintaining the repo's **prose entry surface**: the
`CLAUDE.md` files an agent loads, the `README.md` a human lands on, and the long-form
`<package>/docs/*.md` files both link to.

This skill does **not** cover `docs/features/**`. That is the OKF knowledge graph — ostler
owns its structure and ids, and it is never hand-written. For a story's docs load
[[documentation]]; to model a whole surface graph load [[okf-modeling]]. If you are about to
create a file under `docs/features/`, you are in the wrong skill.

## The four surfaces, and who pays for them

The whole discipline follows from *when* each file is read:

| Surface | Read by | Loaded | Consequence |
| --- | --- | --- | --- |
| `CLAUDE.md` (root) | the agent | **every turn** | the most expensive prose in the repo |
| `CLAUDE.md` (nested) | the agent | every turn *touching that subtree* | free elsewhere — this is the budget lever |
| `README.md` | a human deciding whether/how to use the package | on demand | also the PyPI landing page when published |
| `<package>/docs/*.md` | whoever follows a link | on demand | unbounded; where long-form belongs |
| `docs/features/**` | ostler + agents via `ostler` queries | queried | **not yours** — see [[documentation]] |

`CLAUDE.md` is not documentation. It is a standing instruction loaded into every request,
so every line it carries is a line the agent re-reads forever. Treat it as a budget.

## CLAUDE.md: the admission test

One question decides whether a line belongs:

> **Would a competent agent get this wrong without being told?**

If yes, it goes in. If no, it belongs somewhere else or nowhere. Four disqualifiers, each a
common failure:

1. **Discoverable in five seconds.** Package layout, what a module does, which test runner is
   used — the agent will read the code anyway. An architecture tour is the single most common
   thing wrongly parked in a `CLAUDE.md`.
2. **Generic good practice.** "Write tests", "handle errors", "keep functions small". The
   model already does this; the line buys nothing and dilutes the rules that matter.
3. **Explanation rather than instruction.** *Why* the system works a certain way is README or
   `docs/` material. `CLAUDE.md` carries the rule; the rationale gets one clause, not a
   paragraph.
4. **Already carried by a selected skill.** Two copies of a rule drift, and the agent then
   gets contradictory instructions. Check the repo's `agents.yml` selection first.

What passes is knowledge that is **true, non-obvious, and violated by default** — an
invariant the codebase does not announce, a norm with a tempting wrong alternative, or a fact
that lives outside the tree entirely.

Mark the rules that are invariants rather than preferences with a **`(load-bearing)`** suffix
on their heading. It tells a later reader — human or agent — which sections may not be
trimmed on the next pass.

## Placement: root, nested, skill, README, or docs

| The knowledge is… | It goes to… |
| --- | --- |
| always true, repo-wide, violated by default | root `CLAUDE.md` |
| always true but scoped to one subtree | `<subtree>/CLAUDE.md` |
| relevant only while doing a **task** (writing docs, reviewing, testing, releasing) | a skill — loaded on demand |
| an explanation of how or why the system works | `README.md` |
| long-form reference, design rationale, or an ops procedure | `<package>/docs/<TOPIC>.md` |
| the behavioral spec of a surface, command, or endpoint | `docs/features/**` via [[documentation]] |

The nested `CLAUDE.md` is a **context-budget tool**, not filing. Pushing a rule down one
directory makes it cost nothing on every turn that never goes there. When a root section
applies to exactly one package, moving it down is a pure win.

## `@`-imports are not splitting

A `CLAUDE.md` may inline another file with `@path/to/file.md`. The import is **transitive and
unconditional** — the whole file lands in context on every turn, exactly as if pasted in. So
moving prose out of `CLAUDE.md` and importing it back does not reduce anything; it usually
makes things worse, because the imported file was written for a different reader and never
passed the admission test.

Measure before you decide. What a `CLAUDE.md` actually costs is itself plus everything it
imports:

```bash
wc -c CLAUDE.md $(grep -oP '(?<=^@)\S+' CLAUDE.md)
```

A 45-line `CLAUDE.md` that `@`-imports a 56 KB public README is a ~20k-token standing tax on
every turn in that subtree, and the README's install instructions, pricing tables and `curl`
examples are not instructions to an agent at all.

**Use `@` only when the target is both** (a) itself written to the admission bar, and (b)
needed on *every* turn in that subtree. Otherwise use a plain markdown link and let the agent
open it when the task calls for it — an agent that can read is not helped by pre-loading.

When an import is genuinely earning its place but the target is huge, the fix is usually to
extract the load-bearing part into a small file and import *that*, leaving the rest linked.

## README: what it is for, and when it has outgrown itself

A `README.md` serves a reader who is deciding whether to use the thing and then getting to
first success. Its job is: **what it is → install → a working example → the interface most
users need → where to go deeper.** It is not the reference manual.

Refactor when any of these trip:

- the file is past **~400 lines / ~15 KB**;
- a single section is past **~60 lines**;
- a section a first-time reader would skip sits between them and the quick start;
- you are about to add a second exhaustive table to it.

### What extracts, and what must never leave

Extract, in roughly this order of payoff:

| Extract | Into |
| --- | --- |
| exhaustive reference tables (every env var, every config key, flag matrices) | `docs/<TOPIC>.md` |
| deployment / container / ops procedures | `docs/DOCKER.md`, `docs/DEPLOY.md` |
| design rationale and failure-mode analysis | `docs/<TOPIC>.md` |
| advanced or rare paths (one backend's tuning, a migration route) | `docs/<TOPIC>.md` |
| troubleshooting catalogues | `docs/TROUBLESHOOTING.md` |

Never extract: what the package **is**, how to **install** it, the **60-second quick start**,
the one canonical example, and the **index of links** to everything you moved. Strip those
and the README stops doing its only job.

File naming follows what the repo already does — one topic per file, `SCREAMING-KEBAB.md`
under the package's own `docs/`: `workhorse/docs/GUARDRAILS.md`, `workhorse/docs/DOCKER.md`,
`farrier/docs/LAYOUT.md`, `ostler/docs/ARTIFACT-CONTRACTS.md`. Long-form docs live with their
package, not at the repo root.

### The two rules that make an extraction safe

1. **Leave a summary, not a bare link.** A link with no context is a dead end — the reader
   cannot tell whether following it is worth their time, and an agent grepping the README
   finds nothing. Leave one or two sentences that say what is over there and who needs it,
   then the link.

   ```markdown
   Runs are resilient by default: a flaky node escalates through retry → compact → reframe →
   default rather than ending the run. The full ladder and its env-var knobs are in
   [docs/GUARDRAILS.md](https://github.com/example-org/acme/blob/main/acme/docs/GUARDRAILS.md).
   ```

2. **Use absolute URLs in a published package's README.** A README that ships to PyPI is
   rendered off-repo, where relative links 404. Link to the canonical forge URL
   (`https://github.com/<org>/<repo>/blob/main/<path>`) for anything outside the README
   itself. A README that is never published may use relative links.

### The refactor procedure

1. **Inventory with line counts** so the decision is made on evidence, not feel:
   ```bash
   grep -n '^## ' README.md
   ```
2. **Classify each section** against the extract table above.
3. **Move whole sections.** Never split one across two files — a half-explained knob is worse
   than a long README.
4. **Write the new `docs/<TOPIC>.md`** with its own H1 and enough preamble to stand alone.
   The reader arriving by link has not read the README.
5. **Leave the summary + link** in the README, and add the file to its index of links.
6. **Re-point every inbound reference** — other docs, `CLAUDE.md`, skills, code comments:
   ```bash
   grep -rn "README" --include=*.md --include=*.py . | grep -v node_modules
   ```
7. **Check you did not re-inline it.** If a `CLAUDE.md` `@`-imports the README you just
   shrank, re-measure; extraction that an import undoes is not extraction.
8. **Verify links resolve** — relative paths exist on disk, absolute ones use the real
   default branch.

## Maintenance: drift is the real failure

A stale instruction is worse than a missing one — a missing rule leaves the agent to reason,
a wrong rule actively misleads it.

- **Fix instructions in the same commit as the change that invalidated them.** An instruction
  file is inside the blast radius of a behavior change, exactly like a test.
- **Renames and moves are the usual culprit.** A `CLAUDE.md` naming a directory that no longer
  exists disorients every turn that reads it, before a single rule lands.
- **Delete rules whose reason is gone.** A rule about a retired subsystem is pure cost, and it
  teaches the agent a vocabulary the code no longer uses.
- **Audit periodically**, not only on change. Every command runs, every path exists, every
  claim is still true, no rule duplicates a selected skill.

## Verification before calling the work done

```bash
# 1. Every path, target and command an instruction file names actually exists.
grep -oP '`[^`]+`' CLAUDE.md            # then check the ones that are paths or commands
grep -nE '^(hooks|test|check-public):' Makefile

# 2. The real context cost, imports included.
wc -c CLAUDE.md $(grep -oP '(?<=^@)\S+' CLAUDE.md)

# 3. Nothing under docs/features/ was hand-written by this change.
git diff --name-only | grep '^docs/features/' && echo "use ostler — see [[documentation]]"
```

Then read the file top to bottom once and ask the admission question of every line. Anything
that fails it goes to its place in the placement table, or goes away.

## When to reach for the neighbors

- **A story's behavioral docs, or anything under `docs/features/**`** → [[documentation]]
  (per-story) or [[okf-modeling]] (whole-surface). ostler owns structure and ids there.
- **The `docs/` knowledge-graph CLI, epics, stories, coverage** → [[ostler]].
- **How the material is written, once you know where it goes** — the context pointer and
  what makes it fire, the information hierarchy and the disclosure move down it, completion
  criteria, leading words, the pruning tests → [[agent-writing]]. This skill decides
  *placement*; that one decides *wording*, for a `CLAUDE.md` and a skill alike.
- **Changing a skill, prompt, or pack in the agent library itself** — including this skill —
  → [[agent-library]]. Generated adapter copies under `.claude/`, `.codex/` and
  `.github/` carry a `do_not_edit` metadata key: edit the library source and re-install
  instead.
