# Doctor codes

Every finding `ostler doctor` can raise: **62 codes, 50 error and 12 warn**. An error is a
mechanical defect with a mechanical remedy — the exit code counts errors, so a story can be gated
on it. A warn is a finding whose remedy is authoring judgment, which is why `doctor` cannot
converge on it the way it converges on `fmt`. Companion to [`../SKILL.md`](../SKILL.md); the
claims cluster is the one the story-documentation loop lives in, and its authoring rules are in
[bullet-grammar.md](bullet-grammar.md) and [defect-kinds.md](defect-kinds.md).

Source of truth: `ostler/ostler/doctor.py`. `ostler doctor --json` emits
`{org, profile, epics, errors, warnings, findings}` — `findings` is the list, each entry carrying
`path`, `line`, `code`, `severity`, `ref` and `suggestion`; `errors` and `warnings` are **counts**,
not lists. Keep stderr out of the pipe (`--json 2>/dev/null`, never `2>&1`).

**Waivers downgrade, they do not delete** (`doctor.py:164-176`). A registered waiver flips a
finding to `warn` and sets `waived`, at either severity. Waiving a warn is not cosmetic: the
okf-builder convergence gate drains every finding that is not `waived`, so the register is the
only recorded, diffable way to accept one.

`fixable` findings are the ones `ostler fmt` / `ostler scaffold` / `ostler edit relink` can apply
the remedy for. Reach for the tool before hand-editing.

## What the linter scopes, and what it deliberately does not

Three scoping rules explain findings that otherwise read as false positives or as gaps:

- **Link validation is document-wide, not node-scoped.** `dangling-link` and `missing-anchor` are
  checked for **every** link in **every** doc file, including prose outside any indexed node — so
  a broken link in a paragraph is a finding even though nothing typed surrounds it. Links inside
  fenced code blocks and `` `inline` `` spans are skipped, which is why `arr[i](x)` in a snippet is
  never mistaken for one.
- **`missing-required-bullet` checks that the key is present, not that its value is any good.** A
  key with an empty or stub value clears it — which is exactly why `ostler scaffold`'s stubs leave
  a node doctor-green while still being far below the spec-complete bar. Completeness is a review
  standard, not a doctor gate.
- **`code:` and `tests:` are code refs, not links.** They hold `path::symbol`, and they are
  grounded at a **later QA gate** rather than at author time, so doctor deliberately does not flag
  them as dangling links. `missing-code-symbol` is where that grounding surfaces.

## Freeze

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `frozen-removed` | error | An approved frozen entity no longer exists. Restore it, or `ostler unfreeze <id>` if the removal is intended. |
| `frozen-mutated` | error | A frozen entity changed since approval. Revert it, or `ostler unfreeze <id>` to let it evolve. |

## Epic and story graph

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `cross-epic-seed` | error | A story references a seed belonging to another epic. |
| `dangling-seed` | error | A story references a seed that does not exist. |
| `cross-epic-dependency` | error | A story is blocked by a story from another epic. |
| `dangling-dependency` | error | A story is blocked by a story that does not exist. |
| `malformed-dependency-bullet` | error | A bullet under `## Dependencies` states no blocker. Write it as `- Blocked by: <slug>`. |
| `missing-story-file` | error | A story has no `story.md`. |
| `story-status-mismatch` | error | Frontmatter `status` differs from the `## Implementation Status` value. |
| `unwritten-story` | error | A story is still a bare `ostler create story` scaffold. |
| `story-covers-no-seed` | warn | A story lists no `seedItems`. |
| `orphan-seed` | error | An active seed no story covers. |
| `unclassified-seed` | warn | A seed has no `layers:`, so every covering story keeps the mockup turn by default. |
| `milestone-cycle` | error | A cycle in milestone dependencies. |
| `dangling-milestone-dependency` | error | A milestone depends on a milestone that does not exist. |
| `dangling-milestone-epic` | error | A milestone lists an epic that does not exist. |
| `epic-without-milestone` | error | An epic is assigned to no milestone. |
| `epic-in-multiple-milestones` | error | An epic is assigned to more than one milestone. |
| `backlog-item-in-multiple-milestones` | error | A backlog item is assigned to more than one milestone. |

## Fixtures

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `qa-fixture-declaration` | error | The repo's `qa: {fixtures:}` / `{fixture_modules:}` declaration in `agents.yml` is itself unreadable. |
| `story-fixture-stray` | error | A bullet under `## Fixtures` names no fixture. Write `- Fixture: <name>`, or the declared none-value when the story arranges nothing. |
| `unknown-story-fixture` | error | A story names a fixture this repo does not declare. |
| `undeclared-story-fixture` | error | The story's `qa_plan.py` uses a fixture the story does not list. |
| `unused-story-fixture` | warn | A story names a fixture its `qa_plan.py` never asks for. |
| `qa-fixture-bullet` | error | A `fixture:` bullet in the book is not a fixture reference. |
| `unknown-book-fixture` | error | A `fixture:` bullet names a fixture this repo does not declare. |

## Conformance and structure

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `unreadable` | error | The file could not be parsed. |
| `okf-missing-type` | error | A Concept has no non-empty `type` in frontmatter. Never hand-write the file — `ostler scaffold` / `ostler create` stamps it. |
| `unknown-type` | error | The declared `type:` is not a recognized OKF type. |
| `schema` | warn | A per-type frontmatter schema violation (also raised against `ids.json`). |
| `bad-heading-type` | error | A case or spelling variant of a known UI heading, whose `### id` children would otherwise go unrecognized. `ostler fmt` canonicalizes it. |
| `duplicate-container-heading` | error | Two `## <Title>` sections in one file — the second block's nodes belong to whatever heading precedes them. |
| `missing-required-section` | error | A file type is missing a required `## <Heading>`. `ostler scaffold` stubs it. |
| `empty-required-section` | error | A file type leaves a required `## <Heading>` empty. |
| `missing-required-bullet` | error | A node is missing a `required` bullet. State it, even as `none`. `ostler scaffold` stubs it. |

## Grounding and links

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `dangling-code-ref` | error | A `code:` target names no such file. The value is a path relative to the repo root, as `path::symbol`. |
| `missing-code-symbol` | error | The file exists but does not **declare** that symbol. A re-export does not ground a citation. Read the file, find the symbol that now owns the behaviour, repoint the bullet — never waive it and never restore an old name. |
| `unresolved-relation` | error | A relation bullet (`on:`/`parent:`/`extends:`/`detail:`/…) does not resolve. `fixable`. |
| `dangling-link` | error | A markdown link's target file does not exist. `fixable`. |
| `missing-anchor` | error | The link's file exists but the `#anchor` heading is not in it. `fixable`. |

## Reachability, locators, placement

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `no-entry-point` | warn | No screen on this surface declares `entry:`, so reachability cannot be checked. |
| `unreachable-screen` | error | No documented path reaches a screen. Add a `leads-to:` on the component that navigates there, or `entry:` if it is entered from outside the app. |
| `ambiguous-locator` | error | Two controls on one screen share role+name, so `getByRole` cannot tell them apart. Give each a distinct accessible name — or, if they genuinely never co-render, declare `exclusive-with:`. Also raised when a repeated node's `name:` template — opaque holes wildcarded — pattern-matches a static sibling's literal name. |
| `static-template` | error | A node declares `one-per:` but its `name:` template has no bindable hole, so no consumer can discriminate instances. Write the per-instance datum the render interpolates as a dot-path hole; if the render has none, that is an app a11y defect to record, not a datum to invent. |
| `unproven-unique-name` | warn | The template's bindable holes are display values (`.name`/`.label`/`.title`) and no `unique-by:` claims a distinct key. State `unique-by:` only with evidence from the source; otherwise the warning is the truth. |
| `malformed-template` | error | The `name:` template has an unbalanced brace — the one way a template fails to parse (a hole the dot-path grammar rejects is simply opaque). |
| `malformed-variants` | error | `variants:` does not parse. Form: one backticked span holding `path = token \| token \| …`, prose only after ` — `. |
| `invalid-role` | error | `role:` is not an ARIA role. State the bare computed role and put any caveat in prose. |
| `unnamed-interactive` | error | An operable role with no accessible `name:` — unannounceable to assistive tech and unaddressable by `getByRole`. |
| `missing-placement` | error | A page-carrying role with no `placement:`. A role+name assertion passes on a component crushed into a sliver. |
| `malformed-placement` | error | `placement:` does not parse. Form: `width 60-100%, x 0-20%`. |

## Runbook and environment

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `runbook-missing` | warn | No `runbook` node brings a system up, so QA has no stack to run against. |
| `runbook-bad-reuse` | error | `reuse:` is not an adoption policy (`if-fresh` \| `always` \| `never`). |
| `runbook-bad-kind` | error | A step's `kind:` is not a boot-step kind. |
| `runbook-incomplete` | error | A runbook declares a launch but has no `kind: service` step — nothing starts the system. |
| `runbook-multi-service` | error | More than one `kind: service` step. A runbook brings up one stack; the rest are `kind: prepare`. |
| `runbook-local-only` | error | A runbook boots a `local-only: true` environment that points at a non-local host. |

## Claims and observations

The cluster the story-documentation loop lives in. Each of these has an authoring rule behind
it — see [defect-kinds.md](defect-kinds.md), which maps them to what a documentation review
files.

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `unknown-bullet` | warn | A key that is load-bearing on *some* type used on a type that does not declare it — so here it is inert: nothing orders it, grades it, grounds it, or binds a `verify:` to it. Move the claim under a key this type mints from, or into prose. A key **no** type declares is the author's own vocabulary and is left alone. |
| `overlong-normative-bullet` | error | One normative bullet runs past 700 characters of prose — too much to prove as one claim. Split it into one bullet per provable claim. |
| `relation-without-subject` | warn | A relation bullet names no subject, so no other node can be found to share it. Lead with the record, event or lock it is about. |
| `compound-normative-bullet` | warn | One bullet states more than one observation. One bullet is one obligation proved by one scenario, so the clauses sharing it are covered by whichever one the planner read. Split by repeating the key. |
| `unminted-claim` | warn | A node that mints nothing has a bullet that reads like a claim, under a key this type never grades. Nothing will ever ask a plan to prove it. Move it under a normative key, or into prose. |
| `unparsed-check` | error | A `verify:` value is not a well-formed call. The suggestion echoes **that check's** own signature. A test path here belongs in `tests:`. |
| `weak-check` | error | Every check declared for one claim passes on the defect it is meant to catch. Raised **per claim**, not per node, because the binding of a check to a claim is written down (`attributed_checks`). |
| `unstated-precondition` | warn | A bullet states a lifecycle change and the checks read only the state afterwards — the same state a no-op leaves when the subject was already there. Declare the change as a change: `created(subject=…)` / `removed(subject=…)`. |
| `undeclared-obligation` | warn | A node mints obligations and declares **no** check at all, so a QA plan claiming them can assert anything and still pass. Declare a check per observation; `ostler checks` lists the vocabulary. |
