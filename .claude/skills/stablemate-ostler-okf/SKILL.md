---
name: stablemate-ostler-okf
description: "The OKF UI-profile format and the craft of authoring it — the typed node graph under docs/features/** (screen/cli/server, component/command/endpoint, interaction/invocation, method/field, flow, concept, format, runbook/environment/step), the three content rules (the book not a changelog, spec-complete, spec not implementation), the scaffold→author→fmt→doctor loop, the bullet grammar, the check vocabulary behind `verify:` and the bar a check clears to be an observation at all. Load whenever you are writing or repairing anything under docs/features/ — a one-story merge after finishing a story, a bulk build of a whole service's surface graph, a prose-only feature doc, or a doctor finding."
metadata:
  generated_by: farrier
  source: library/skills/ostler/ostler-okf/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-ostler-okf/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [standards, docs]
---

# OKF — the book under `docs/features/`

Load this skill whenever you write or repair anything under `docs/features/`. Three jobs reach
it, and they share this page:

- **A story is finished** and its delta has to be merged into the book — the common case.
- **A whole service's surface graph** is being built or backfilled in bulk →
  [references/bulk-build.md](references/bulk-build.md) after this page, then the playbook for your
  input: [from a description](references/from-description.md) or
  [from existing code](references/from-code.md).
- **A prose-only reference** with no enumerable surface → the plain `feature` type,
  [references/plain-feature.md](references/plain-feature.md).

The tool that reads and writes the graph — every command, the Python API, the planning graph of
epics and stories that sits beside it — is [[ostler-cli]]. This page is the *format* it enforces.

## The golden rule

**`docs/` is a knowledge graph, not a folder of loose markdown.** Every doc is an OKF (Open
Knowledge Format) **Concept**: one `.md` file with YAML frontmatter (hard requirement — a
non-empty `type`) plus a markdown body, its identity being its path. **ostler owns the structure
and the ids; you author the prose into the skeleton it scaffolds.** Never hand-invent frontmatter
or a `docs/features/` path — call `ostler` so the file is conformant and `ostler doctor` stays
green.

## Three rules govern *what* you write

1. **The book, not a changelog.** The graph is the **full, always-current spec** of the system. A
   story is a **delta** — so **merge it into the book**: edit the affected nodes until they
   describe the new current reality completely. Never write "this story added X"; a reader who
   never saw the story must get the whole, correct spec. (The story stays in `docs/epics/**`.)
2. **Spec-complete — enough to regenerate the code.** A node carries every field with its
   type/default/required, every flag and arg item-by-item, every effect and guard, the algorithm
   as ordered steps, errors and exit codes, and for UI the role/name/placement contract. A
   one-line stub is below bar. The per-type bar is the type's own reference below.
3. **Spec, not implementation.** Document *what* the code does — the behaviour and the contract.
   Do **not** write coding patterns, idioms, or library and structure choices; those are owned by
   the stack skills (`go`, `react-router`, `python-testing`, …), never the book. `code:`/`tests:`
   anchor the current implementation; the prose never prescribes a technique.

Completeness is a **review** standard — the doc gates and the auditor — not a `doctor` gate. A
linter cannot judge "enough to regenerate."

## The written model — one reference per node type

There are sixteen types. They sort by **role**, which is how you pick one, and each links its own
reference — the authority wherever this page and it disagree.

| Role | GUI | CLI | HTTP/WS | context-free |
|---|---|---|---|---|
| **surface** — you interact with it | [`screen`](references/node-types/screen.md) | [`cli`](references/node-types/cli.md) | [`server`](references/node-types/server.md) | |
| **element** — part of a surface | [`component`](references/node-types/component.md) | [`command`](references/node-types/command.md) | [`endpoint`](references/node-types/endpoint.md) | |
| **behaviour** — one event or call | [`interaction`](references/node-types/interaction.md) | [`invocation`](references/node-types/invocation.md) | [`invocation`](references/node-types/invocation.md) | |
| **member** — of a concept or format | | | | [`method`](references/node-types/method.md), [`field`](references/node-types/field.md) |
| **journey** — an ordered path | | | | [`flow`](references/node-types/flow.md) |
| **noun** — domain *or* code | | | | [`concept`](references/node-types/concept.md) |
| **artifact / data shape** | | | | [`format`](references/node-types/format.md) |
| **operations** | | | | [`runbook`](references/node-types/runbook.md), [`environment`](references/node-types/environment.md), [`step`](references/node-types/step.md) |

Each reference gives what the type is and when to reach for it rather than its neighbours, its
identity (file or section, its folder or heading), its bullet keys in canonical order, its
required sections, its relationships, a minimal example with the `ostler scaffold` line that
produces it, and the doctor codes it can trip.

Four more references cut across every type:

- [bullet-grammar.md](references/bullet-grammar.md) — the bullet-key flags, the four key
  families, the shared normative keys, ownership, one-provable-claim, and **document order is the
  binding** (which `verify:` and which `fixture:` attach to which claim).
- [check-vocabulary.md](references/check-vocabulary.md) — all 14 checks with their signatures
  and, for each, **the defect it excludes**. `ostler checks [--json]` prints the same thing live.
- [doctor-codes.md](references/doctor-codes.md) — every finding `ostler doctor` can raise,
  grouped, with its trigger and its remedy.
- [defect-kinds.md](references/defect-kinds.md) — the eight defect kinds a documentation review
  files, each anchored to the rule and the doctor code behind it.

**Judgment does not live in bullets.** A registry can say what a node *is*; it can never say
whether you should be using it. Two services that do the same job — one legacy, one current, each
right in a different context — both produce conformant nodes, and doctor is green on both. That
selection rule belongs in a [`concept`](references/node-types/concept.md), the one type with no
normative keys, linked from each competing node with `detail:`.

## Where a node lives, and how it links

**File vs section is the author's choice.** A node is either its **own file** (identity = path;
every top-level `concept` gets one so others can link it) or a **section** inside a larger doc,
identified by `path#anchor`. A section gets its type two ways — whichever reads best:

- **container heading** — a `### <id>` under a typed `## Heading`: `## Components`→`component`,
  `## Commands`→`command`, `## Endpoints`→`endpoint`, `## Interactions`→`interaction`,
  `## Invocations`→`invocation`, `## Methods`→`method`, `## Fields`→`field`.
- **inline `type:` prefix** — `## concept: the agent node runs a turn`, `### field: timeout` —
  the token before the first `:` is the type, the rest is a human summary.

**Sections nest.** A typed section's typed descendants become its children at any depth, so a
`concept` can hold `### method:`s and a `format` can hold `### field:`s, and `ostler graph --path
'concept:agent / field:timeout'` walks straight to it. **Don't bury spec in prose** — a field
described in a sentence is invisible to `ostler graph`; the same thing as a nested typed section
is a first-class node you can query. Put a member's filterable attributes in its own bullets
(`sig:`/`abstract:`/`raises:` for a method, `type:`/`default:`/`required:` for a field), one per
attribute, never crammed into a line. Reserve prose for the summary.

**Layout is per service, then by context.** Each service owns `docs/features/<service>/`, split
into `gui/`, `http/`, `cli/` only if it genuinely spans contexts; `concepts/` and `flows/` sit at
the service root. Don't hand-pick paths — `ostler scaffold` places every node for you.

**Links are plain markdown path links, never `[[wikilinks]]`** — `[diff](../concepts/diff.md)`,
`[row](changes-view.md#changes-file-row)`, same-file `[row](#changes-file-row)`. A bare link is
**neutral**; meaning lives in the prose beside it. Two optional relation bullets layer a name on
a link: `parent:` (part-of) and `extends:` (is-a). A selector chooses one implementation of an
abstraction via a plain `refs:` link.

**No orphans.** Everything must be reachable by `ostler trace` from the `screen`/`cli`/`server`
index, which links its key concepts and formats in its own intro region — the part before the
first `##`, which is what `trace` surfaces and the linter checks. Put structural pointers in the
node's bullets, not only in prose.

**Document flags and arguments item-by-item, not as a token dump.** `- flags: --a, --b, --c` with
no explanation is a smell: write a nested bullet list, one child per flag or positional, each
saying what it does and in which context it applies, linking the `concept`/`format`/command it
touches.

**Every interactive control carries its accessibility contract** — `role:`, `name:`, `keyboard:`
on the `component`/`interaction` node. This is the same data twice over: it is what makes the UI
accessible **and** the robust basis for automation, since an interaction maps to
`getByRole(role, {name})` — stable across CSS churn — with the brittle `selector:` only as a
fallback. A control you cannot give a role and an accessible name is an a11y gap *and* a doc gap;
flag it, don't paper over it with a class selector.

**Every structural component says where it sits** — a `placement:` bullet of viewport bands, and
it is the only bullet that can tell a correct page from one crushed into a narrow column, since
`role:` and `selector:` hold either way. Read the numbers off the running UI, never invent them;
**state a band, never a point**; never widen one to make a red run green. Leaf controls get none.
The grammar and the required keys are in [component.md](references/node-types/component.md) and
[interaction.md](references/node-types/interaction.md).

## The loop — scaffold → author → fmt → doctor

Never hand-write the file.

1. **Find what already exists**, so you don't duplicate a node:
   ```bash
   ostler list --type screen --json      # or component/interaction/cli/command/endpoint/concept/…
   ostler search <slug> --json           # ostler trace <id|slug|anchor>
   ```

2. **Scaffold what ostler doesn't have yet** — this places the node in its canonical path or
   heading with conformant frontmatter, the H1, bullet **stubs**, and (for surfaces) the
   required-section skeleton:
   ```bash
   # a file-level surface/concept → docs/features/<service>/<context>/<name>.md
   ostler scaffold screen changes-view --service groom --title "Changes view"
   ostler scaffold concept diff       --service groom --title "Diff"

   # a section-level element/behaviour → a `### id` under its typed `## Heading`
   ostler scaffold interaction click-file-opens-diff --in docs/features/groom/gui/screens/changes-view.md
   ostler scaffold command  run --in docs/features/workhorse/workhorse.md
   ```
   If the node **already exists, there is no scaffold call** — edit its body and bullets in place
   and go to step 4. Preserve the frontmatter `type`/`slug`; those are the graph identity. To move
   or rename one so links follow, `ostler edit rename/relink … --write` (dry-run by default).

3. **Author to the spec-complete bar, merging your delta in.** Edit the `.md` directly — the body
   is the sanctioned surface. If the node already existed, **merge** so it reads as the complete
   current spec (rule 1); don't bolt on a note. Fill the structured bullets to the per-type bar
   (rule 2). Describe behaviour, not coding patterns (rule 3). Since you just wrote the code, set
   `code:`/`tests:` to the real `path::symbol` and `verify:` to the observation that proves the
   node:
   ```markdown
   ### click-file-opens-diff
   - on: [changes-file-row](#changes-file-row)
   - trigger: click
   - when: `mode == changes`
   - does:
     - state: mark row `.active`, clear siblings
     - dom: render single-file diff
   - code: `groom/groom/templates/dashboard.html::wireChanges`
   - verify: visible(locator="single-file diff")
   - tests: `groom/tests/test_render.py::test_changes_groups_diffs_per_repo`
   ```

4. **Canonicalize, then gate:**
   ```bash
   ostler fmt docs/features/<service>/…   # frontmatter/bullet/heading shape — never touches prose
   ostler doctor                           # non-zero exit on any error — safe to gate the story on
   ```
   `ostler fmt` is the mechanical shape-fixer, the `ruff format` to doctor's `ruff check`. Every
   doctor error has a mechanical remedy: fmt fixes casing and order, scaffold stubs a missing
   section or bullet, you fix a broken link. Never silence a finding by deleting the bullet that
   carried the meaning. Every code, its severity, its trigger and its remedy is in
   [doctor-codes.md](references/doctor-codes.md), which also carries the `--json` shape, the
   waiver semantics, and what the linter does and does not scope. Keep stderr out of the pipe
   (`--json 2>/dev/null`, never `2>&1`): one warning line on stdout makes the document
   unparseable, and the parse error that follows looks exactly like having picked the wrong key.

## Three bullets, three grammars

They are not interchangeable, and each is machine-checked.

| Bullet    | Holds                                 | Checked by `doctor` against                                |
| --------- | ------------------------------------- | ---------------------------------------------------------- |
| `code:`   | `` `path::symbol` `` — where it lives | the file existing *and* the symbol being **declared** there |
| `tests:`  | `` `path::test_name` `` — what ran    | the same grounding as `code:`                               |
| `verify:` | `name(arg=…)` — what was **observed** | the check vocabulary and that check's signature             |

A test id in `verify:` is the single most common refusal, and it is a category error, not a typo:
a test id says which code *ran*, which is what `tests:` is for; `verify:` says what was *seen*, so
an assertion can never come out weaker than the claim filed under it.

**`code:` is grounded part-wise, and a refactor breaks it.** `missing-code-symbol` means the
symbol is not declared at that path *today* — a re-export does not ground a citation, and a
constant dissolved into a function during your own refactor no longer exists to cite even though
the behaviour survived. Cite what the code now declares; never waive the finding or restore the
old name. Verify with `rg` before you rewrite the bullet — an explanation of where the symbol
"really lives" that you did not check in the source is a guess, and it costs a whole gate lap.

## `verify:` — declaring the observation

Every normative bullet mints a QA obligation, and `verify:` is where the node says **what would
be observed** if that obligation holds. It is a call from ostler's check vocabulary with typed
arguments, never a test id and never prose:

```markdown
- does: on conflict the manifest is left byte-identical
- verify: unchanged(subject="manifest", except_fields=["pages.getting-started.fr.slug"])
- verify: http_status(409, title="Manifest Conflict")
- tests: `api/publish_test.go::TestPublish_Conflict`
```

**Never guess a check's arguments — read them.** `absent` takes `subject`, not `locator`;
`emitted` takes `event`, not `subject`. `ostler checks` (or `ostler checks visible`) prints every
signature with the defect it excludes, and [check-vocabulary.md](references/check-vocabulary.md)
has the same table in prose. Read one *before* writing a `verify:` you have not written before,
not after doctor refuses it.

`doctor` grounds each call against the vocabulary (`unparsed-check`, an **error**), `ostler qa
validate` refuses a QA plan that claims the obligation without invoking the declared call with the
declared arguments, and the harness implements each name. That chain is the point: **an assertion
cannot come out weaker than the declaration, because the assertion *is* the declaration.** Every
argument you leave off is a defect the QA of every future story is licensed to miss, and nobody
downstream can put it back, because only this node knows what the behaviour promised.

**One provable claim per normative bullet.** Each value of a normative key becomes **one QA
obligation**, proved by **one scenario**, and doctor errors past 700 characters of prose. Merging
a delta into a sentence that already holds three requirements produces a bullet where the scenario
proves whichever clause the planner read and the rest ships claimed-as-covered. Split on the real
seams — the success effect, each error case, what is persisted, what is emitted — by repeating the
key; only you know which clauses are separate requirements. Which keys are normative is per type,
in the type's reference; the shared ones and the document-order binding are in
[bullet-grammar.md](references/bullet-grammar.md).

**Every obligation-minting node declares at least one observation.** A node that states claims and
no `verify:` is `undeclared-obligation` — a QA plan claiming it can assert anything and still
pass. It is a warning rather than an error only because books written before the rule are full of
them; treat it as queued work, not noise.

A declared check is not automatically an observation. The bar — name the state of the world in
which the check goes red, assert the before-state rather than assuming it, discriminate the claim
from its nearest plausible defect — and the two shapes a linter can see (`weak-check`,
`unstated-precondition`) are in
[falsifiable-verification.md](references/falsifiable-verification.md). Read it when you are
writing checks in bulk, repairing one of those findings, or reviewing checks somebody else
declared.

## Neighbours

- **The tool** — every CLI command, the `from ostler import Ostler` Python API, the planning graph
  of epics, stories and seeds, id allocation, the QA control plane → [[ostler-cli]].
- **The repo's own prose entry surface** — `CLAUDE.md`, `README.md`, `<package>/docs/*.md` →
  [[ostler-repo-docs]]. That is not this graph.
