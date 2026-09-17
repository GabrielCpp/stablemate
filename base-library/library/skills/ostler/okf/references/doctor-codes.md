# Doctor codes

Every finding `ostler doctor` can raise: **100 codes, 80 error and 20 warn**. An error is a
mechanical defect with a mechanical remedy — the exit code counts errors, so a story can be gated
on it. A warn is a finding whose remedy is authoring judgment, which is why `doctor` cannot
converge on it the way it converges on `fmt`. Companion to [`../SKILL.md`](../SKILL.md); the
claims cluster is the one the story-documentation loop lives in, and its authoring rules are in
[bullet-grammar.md](bullet-grammar.md) and [defect-kinds.md](defect-kinds.md).

Source of truth: `ostler/ostler/doctor.py`. `ostler doctor --json` emits
`{org, profile, epics, errors, warnings, findings}` — `findings` is the list, each entry carrying
`path`, `line`, `code`, `severity`, `ref` and `suggestion`; `errors` and `warnings` are **counts**,
not lists. Keep stderr out of the pipe (`--json 2>/dev/null`, never `2>&1`).

**There is no waiver register.** A finding leaves the report inside the book: repaired, excused
by a `known-defect:` bullet naming the seed that fixes the code (honoured while the seed is open,
`stale-defect` afterwards), or scoped out by a surface's `exercised: false` declaration. Each of
those has a mechanical exit; a register entry had none, which is why it is gone.

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
- **A surface can declare itself not exercised.** `exercised: false` in the frontmatter of
  `docs/features/<surface>/index.md` (a reserved file no loader reads as a node) drops the
  obligation-class findings under that surface — `undeclared-obligation`, `unminted-claim`,
  `compound-normative-bullet`, `weak-check`, `insensitive-check`, `unstated-precondition`,
  `relation-without-subject`. A legacy app kept documented while nothing drives it is not owed a
  check per claim, because no QA plan will ever be asked to prove one. Everything mechanical
  still fires — a dangling link, a missing bullet, a locator collision are about the book. The
  declaration has two exits: `malformed-declaration` when the value is not a boolean, and
  `stale-declaration` when the surface has no node left to cover.
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
| `story-id-mismatch` | error | The immutable id in a story's parent epic block differs from the id in `story.md`. Make the two copies agree; do not mint a replacement. |
| `story-key-collision` | error | One id, slug, or provider-neutral `externalKey` names multiple stories. Keep every accepted story spelling graph-global and unambiguous. |
| `story-status-mismatch` | error | Frontmatter `status` differs from the `## Implementation Status` value. |
| `unwritten-story` | error | A story is still a bare `ostler create story` scaffold. |
| `story-section-order` | error | A story carries its required sections out of contract order. |
| `story-conflict` | error | The story's frontmatter `conflict:` records two acceptance criteria that cannot both hold — the adjudicator's `story` verdict, with its chain. Rewriting intent is the operator's: edit the criteria so one intent holds, then `ostler conflict <slug> --clear`. |
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
| `qa-fixture-declaration` | error | The repo's `qa: {fixtures:}` declaration in `agents.yml` is itself unreadable. |
| `story-fixture-stray` | error | A bullet under `## Fixtures` names no fixture. Write `- Fixture: <name>`, or the declared none-value when the story arranges nothing. |
| `unknown-story-fixture` | error | A story names a fixture this repo does not declare. The repair depends on the story's own `qa_plan.py`, and the finding's `suggestion` carries whichever one the plan supports: the plan asks for the name, so declare it; the plan never asks for it, so nothing arranges it and nothing wants it — delete the bullet, or write the declared none-value; there is no plan yet, so neither repair is supported and the finding prescribes nothing. A name is reported here once and only once — it is never also an `unused-story-fixture`. |
| `undeclared-story-fixture` | error | The story's `qa_plan.py` uses a fixture the story does not list. |
| `unused-story-fixture` | warn | A story names a **declared** fixture its `qa_plan.py` never asks for. An undeclared one is `unknown-story-fixture` alone. |
| `unmigrated-fixture-declaration` | warn | A hand-written `qa: {fixtures:}` entry has no book fixture node behind it yet — a candidate for `ostler qa fixtures migrate`. |
| `qa-fixture-bullet` | error | A `fixture:` bullet in the book is not a fixture reference. |
| `unknown-book-fixture` | error | A `fixture:` bullet, or an `@<id>` reference, names a fixture (or fixture key) this repo does not declare — including a `fixture:` bullet on `environment`/`command`/`endpoint`/`interaction`/`invocation`/`method`/`field` naming no [`fixture`](node-types/fixture.md) node. |
| `fixture-step-kind` | error | A `fixture` node's own `## Steps` uses a `kind:` outside `seed`/`run`/`verify` — narrower than a runbook step's kinds, because a fixture only ever seeds, runs, or verifies. |
| `fixture-step-no-run` | error | A `fixture` node's own step carries no `run:` bullet — it would execute nothing, leaving the fixture incomplete with no signal at run time. |
| `fixture-arg-mismatch` | error | A `fixture:` bullet's `name=value` args do not match the target fixture's declared `args:` (after crediting args the target's own `needs:` bindings already supply), or a fixture's own `needs:` binding names an arg it does not itself declare under `args:`. |
| `fixture-needs-target-args` | error | A `needs:` link's target itself declares `args:` — runtime always runs a needs target with no args (it is a shared, once-per-scenario dependency), so a needs target's own `args:` can never be satisfied. |
| `fixture-needs-cycle` | error | A fixture's `needs:` chain cycles back to itself. |
| `fixture-undeclared-provides` | error | An `@<fixture>.<key>` reference names a key the target fixture's `provides:` does not declare at all. (A key it declares but has not yet arranged earlier in the scenario is `unresolved-precondition`, not this — order is `compile_plan`'s concern, not doctor's.) |
| `unbacked-precondition` | warn | A `fixture:` bullet states prose after an em dash — the state the arrangement leaves behind — and the book fixture node it names declares no `provides:` at all. The precondition is written by the node that *uses* the arrangement about work the node that *performs* it never claimed, and `qa compile-plan` copies it into `preconditions=[...]` where nothing can hold the fixture to it. Fix it on the producer: one `provides:` child per fact, `<key> — <what it means>`. |
| `fixture-secret-name` | error | A fixture's `secrets:` child is not a valid environment-variable name — it declares NAMES only, resolved from the harness's own environment at run time, never a value or a mint recipe. |
| `unresolved-precondition` | error | `compile_plan` could not reach the state an obligation's check observes: no fixture arranged it, an `@node.key`/`$name` reference in a path or a `verify:` argument names a fact no earlier producer in the scenario left behind, the book carries no request body, or a route's path still carries a template variable. Raised from `Gap`s via `doctor.gap_findings`, against one compiled plan and its context packet — never by walking the book alone. |
| `uncompilable-claim` | error | An obligation `compile_plan` had no action to compile at all: the book gives the node no `route:`, or a declared check (`unchanged`, `persists`, …) observes a before/after subject the book never named. Raised the same way as `unresolved-precondition`, from the same `Gap` list. |
| `unresolved-extends` | error | An `interaction`/`invocation` arm's `extends:` link resolves to no same-type node — either it does not resolve at all (also `unresolved-relation`, from walking the book alone) or it resolves to a different node type (also `extends-type-mismatch`, likewise from the book alone). Either way, `qa/context.py` could not inherit the base case's `on:`/`trigger:`/`role:`/`name:`/`keyboard:`, so `compile_plan` gapped every obligation the arm mints. Raised from `Gap`s, against one compiled plan and its context packet. |
| `screen-preconditions-undeclared` | error | A screen is reachable, but declares no `requires:`/`params:` bullets at all — so `compile_plan` can open it and cannot say what state it must be opened *in*. Raised once per screen rather than once per obligation (the deliberate exception to the per-obligation rule): every `visible(...)` bullet on the screen shares the identical fact, and multiplying it by obligation count adds no information. The finding still carries a real obligation id — the first, sorted — standing in for the screen. Raised from `Gap`s, like the rest of this family. |
| `needs-snapshot` | error | The obligation's check observes a subject *before and after* the action — a `subject-pair` check — and the compiler has no snapshot mechanism to take the pair with. Hand it the pair explicitly. Raised from `Gap`s. |
| `needs-out-of-band-observation` | error | The obligation's check observes a subject read through a channel the compiler has no handle on (`checks.OUT_OF_BAND`) — a mailbox, a log, a queue. The claim is not wrong and the book is not at fault; the arrangement simply has to happen outside the compiled plan. Raised from `Gap`s. |
| `undeclared-entry-url` | error | The obligation's surface states no `entry-url:` on any `server` or `runbook` node, and `compile-plan` was given no `--base-url` to fall back on — so there is no address to drive the surface at and every obligation on it is dropped from the plan. State the surface's address in its book (a service's address is a property of the service), rather than passing it per run. Raised from `Gap`s. |
| `extends-type-mismatch` | error | An `interaction`/`invocation` node's `extends:` link resolves, but to a node of a different type — an arm can only extend a base case of its own node type. Raised by walking the book alone, before any plan compiles. |
| `unspelled-alternation` | warn | An `interaction`/`invocation`'s `verify:` bullets call the same check with the same identifying argument (the same `path=`, the same `locator=`) but a different value for whichever argument is left — one node claiming two outcomes for the same subject at once. The repair is `extends:` (D51): split into a base case and an arm, each keeping the `verify:` that is true of it. Raised by walking the book alone. |

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
| `missing-required-bullet` | error | A node is missing a `required` bullet. State it, even as `none`. `ostler scaffold` stubs it. An `interaction`/`invocation` arm's `on:`/`trigger:`/`role:`/`name:`/`keyboard:` is exempt when it states a valid same-type `extends:` (D51) — it inherits the base case's control identity instead of restating it. |

## Grounding and links

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `dangling-code-ref` | error | A `code:` target names no such file. The value is a path relative to the repo root, as `path::symbol`. |
| `directory-code-ref` | error | A `code:` target names a directory, not a file. Cite the specific file that declares the symbol. |
| `test-subject` | error | Every `code:` citation on the node is test source — a mock, a fake in a `_test.go`, a fixture (`refs.is_test_source`). A book documents product behaviour a user can observe; the test suite's doubles are an implementation detail. Delete the node — the whole page when it is the page's own node — and the links into it. Never repoint it at production code to keep it. |
| `code-cites-test` | error | The node cites production code *and* test source. Remove the test citations from `code:`; a test that proves the claim goes under `tests:` where the type admits it. |
| `missing-code-symbol` | error | The file exists but does not **declare** that symbol. A re-export does not ground a citation. Read the file, find the symbol that now owns the behaviour, repoint the bullet — never waive it and never restore an old name. |
| `undecodable-code-symbol` | error | A `code:` target names a `path::symbol`, but the file is not valid UTF-8, so the symbol grounding check cannot read it. Cite a decodable source file, or drop `::symbol` for a whole-file unit. |
| `stale-citation` | error | A local `code:` target's `@digest` stamp disagrees with the file's current content — the citation was stamped, then the file changed under it. Re-read the file and correct the node's claims if they no longer hold; the citation is restamped when the turn commits — never hand-write the digest. |
| `unstamped-citation` | warn | A local `code:` target carries no `@digest` yet. Stamped automatically when a turn that edits this node commits, or by the one-time catalog migration — never hand-write the digest, and never invoke `ostler stamp` yourself. |
| `unreachable-citation` | warn | A repository-qualified `code:` target names a repository this run was given no checkout for — there is nothing under this run to check the citation against. Pass `--checkout <repository>=<path>`; not a fix to the book. |
| `unresolved-relation` | error | A relation bullet (`on:`/`parent:`/`extends:`/`detail:`/…) does not resolve. `fixable`. |
| `dangling-link` | error | A markdown link's target file does not exist. `fixable`. |
| `missing-anchor` | error | The link's file exists but the `#anchor` heading is not in it. `fixable`. |

## Reachability, locators, placement

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `no-root-screen` | warn | No screen on this surface has the root `route:` — the path of its `walkthrough: true` server's `entry-url:`, or `/` — so reachability cannot be checked. Document the screen the app opens on. |
| `unreachable-screen` | error | No documented path reaches a screen from the surface's root. Add a `leads-to:` on the component that navigates there, or `entry: /<route>` if it is entered from outside the app. A prose `entry:` does not exempt: a walk can open an address, not a description. |
| `ambiguous-locator` | error | Two controls on one screen share role+name, so `getByRole` cannot tell them apart. Give each a distinct accessible name — or, if they genuinely never co-render, declare `exclusive-with:`. Also raised when a repeated node's `name:` template — opaque holes wildcarded — pattern-matches a static sibling's literal name. |
| `duplicate-bullet` | error | A component states `role:` or `name:` more than once. A control has one of each, so the node cannot say which it is and `collisions` skips it until it is well-formed — this is a book defect, never a locator collision. Keep the bullet the source renders and drop the rest. |
| `stale-defect` | error | A `known-defect:` record has outlived its work: the seed it names is resolved, dropped, deferred or unknown, or the finding it excused no longer fires. The excused finding is back in the report. Fix the code under an active seed, or drop the bullet. |
| `malformed-defect` | error | A `known-defect:` value does not state `<seed-id> <finding-code>`. A code with no seed is a waiver; a seed with no code excuses everything. |
| `static-template` | error | A node declares `one-per:` but its `name:` template has no bindable hole, so no consumer can discriminate instances. Write the per-instance datum the render interpolates as a dot-path hole; if the render has none, that is an app a11y defect to record, not a datum to invent. |
| `unproven-unique-name` | warn | The template's bindable holes are display values (`.name`/`.label`/`.title`) and no `unique-by:` claims a distinct key. State `unique-by:` only with evidence from the source; otherwise the warning is the truth. |
| `malformed-template` | error | The `name:` template has an unbalanced brace — the one way a template fails to parse (a hole the dot-path grammar rejects is simply opaque). |
| `malformed-variants` | error | `variants:` does not parse. Form: one backticked span holding `path = token \| token \| …`, prose only after ` — `. |
| `template-outside-repeat` | warn | The `name:` carries balanced `{…}` holes but the node declares no `one-per:` and inherits no repeat scope — every hole is opaque, so consumers match the name as a wildcard instead of the value it was written to pin. Declare the repeat keys if the control renders per member of a collection; otherwise write the literal rendered name. A warn per the migration rule: backfills drain conversions as ordinary worklist items. |
| `invalid-role` | error | `role:` is not an ARIA role. State the bare computed role and put any caveat in prose. |
| `unnamed-interactive` | error | An operable role with no accessible `name:` — unannounceable to assistive tech and unaddressable by `getByRole`. |
| `missing-placement` | error | A page-carrying role with no `placement:`. A role+name assertion passes on a component crushed into a sliver. |
| `malformed-placement` | error | `placement:` does not parse. Form: `width 60-100%, x 0-20%`. |
| `unaddressable-selector` | error | A component's `selector:` is a form the render scan never mints — it addresses only by `#id`, `tag.class` (optionally `:nth(i)`), or `tag[role="..."]`. Any other attribute predicate reads `missing` on every render, so the census can never confirm it. Address the element by id, class, or role; if the distinction is a piece of state (`data-state="booked"`, `[disabled]`), record it on `states:` instead and write the distinguishing check as a raw-CSS `verify: visible(locator=...)` — that path compiles straight to a live locator and never goes through the census. |

## Runbook and environment

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `runbook-missing` | warn | No `runbook` node brings a system up, so QA has no stack to run against. |
| `runbook-bad-reuse` | error | `reuse:` is not an adoption policy (`if-fresh` \| `always` \| `never`). |
| `runbook-bad-kind` | error | A step's `kind:` is not a boot-step kind. |
| `runbook-incomplete` | error | A runbook declares a launch but has no `kind: service` step — nothing starts the system. |
| `runbook-multi-service` | error | More than one `kind: service` step. A runbook brings up one stack; the rest are `kind: prepare`. |
| `runbook-local-only` | error | A runbook boots a `local-only: true` environment that points at a non-local host. |
| `check-expression-as-command` | error | A `run:`/`health:` bullet on a `step` (a runbook's or a fixture's) parses as a check expression (`checks.parse_check`), not a shell command — `ensure_stack`/the fixture harness shell this bullet verbatim, so this would fail with a bash syntax error at bring-up time rather than run. Write a shell command that exits non-zero on failure (`curl -fsS <url>`), or move the check onto the `verify:` of the claim it actually observes. |

## Claims and observations

The cluster the story-documentation loop lives in. Each of these has an authoring rule behind
it — see [defect-kinds.md](defect-kinds.md), which maps them to what a documentation review
files.

| Code | Sev | Trigger and remedy |
| --- | --- | --- |
| `unknown-bullet` | warn | A key that is load-bearing on *some* type used on a type that does not declare it — so here it is inert: nothing orders it, grades it, grounds it, or binds a `verify:` to it. Move the claim under a key this type mints from, or into prose. A key **no** type declares is the author's own vocabulary and is left alone. |
| `overlong-normative-bullet` | error | One normative bullet runs past 700 characters of prose — too much to prove as one claim. Split it into one bullet per provable claim. |
| `relation-without-subject` | warn | A relation bullet names no subject, so no other node can be found to share it. Lead with the record, event or lock it is about, as one lowercase slug before a spaced em dash — `- persistence: payout-record — …`. A Title Case name or a leading phrase is prose to the parser, not a subject. |
| `compound-normative-bullet` | warn | One bullet states more than one observation. One bullet is one obligation proved by one scenario, so the clauses sharing it are covered by whichever one the planner read. Split by repeating the key. A clause after a semicolon that only explains the one before it is no observation: keep it as a parenthetical aside, which this rule does not read. |
| `unchecked-availability-state` | warn | A `states:` bullet says the user cannot act on the control — `disabled`, `greyed`, `read-only` — and no `actionable(...)`/`inert(...)` call anywhere in the book names that node. `visible(...)` does not observe this: a greyed-out button is on the screen and reads the right label. Write the claim as what the user can do (`inert(locator="#the-control")`), not as the attribute one rendering spells it with. |
| `unminted-claim` | warn | A node that mints nothing has a bullet that reads like a claim, under a key this type never grades. Nothing will ever ask a plan to prove it. Move it under a normative key, or into prose. |
| `unparsed-check` | error | A `verify:` value is not a well-formed call. The suggestion echoes **that check's** own signature. A test path here belongs in `tests:`. |
| `undeclared-check-locator` | error | A check argument marked *(locator)* points at a raw selector or at an anchor no `component`/`interaction` declares. A locator is a reference into the book — `#anchor` in the same document, `path/doc.md#anchor` across documents — so the selector lives in exactly one place and renaming the element shows up here rather than as a red run against an undisturbed book. A navigation interaction is the usual offender and usually wants the destination *screen*, not an element on it. |
| `unstated-claim-combiner` | error | A nested claim list holds more than one child and has a `verify:` written under it, and does not say whether the children are parts of one effect or alternative outcomes. Fan-out is sound over a conjunction and unsound over a disjunction: against `page stays put`, a check written for the success branch is a *refutation*, and an unqualified fan-out files it as a proof. State the word in the parent's own value — `- does: all` or `- does: branches` — where it is not a claim and mints no obligation. It is stated rather than derived from the child labels, because a label the vocabulary did not anticipate would read as `all`, which is the unsound direction. A list nobody observes needs no word. |
| `unobserved-branch` | warn | A child of a list declared `branches` has no check of its own, and the `verify:` under the list was written for a sibling outcome — so nothing observes this branch and nothing may. The remedy is not a word: split the alternatives into sibling authored bullets, each carrying the check that is true of it, which is the only shape a branch's own check can exist in. |
| `weak-check` | error | Every check declared for one claim passes on the defect it is meant to catch. Raised **per claim**, not per node, because the binding of a check to a claim is written down (`attributed_checks`). |
| `insensitive-check` | error | Every check declared for one claim stayed green through every perturbation `ostler qa sensitivity` tried against it — a synthesized witness observation survived every mutation a real defect would have caused. `weak-check` catches the two spellings that are statically a rubber stamp; this is the same finding widened to the experimental method. Raised **per claim**. Assert a value the defect would actually change: the route, the field's content, or the title the claim turns on. |
| `unwitnessed-check` | warn | `ostler qa sensitivity` could not build a witness observation any check on this claim accepts, so **no perturbation was tried** and the experiment has no result. Not a weaker `insensitive-check` and not a finding about the check: the subject is the reach of the harness. It falls hardest on the *most* specific patterns a book writes — an alternation, a negative lookahead, a multiline anchor — because those are the ones `_matching` cannot invent a member of, so the one edit that would silence it (a looser pattern) is the edit that would make `insensitive-check` genuinely true. Leave the check standing unless it is wrong on its own merits. |
| `unstated-precondition` | warn | A bullet states a lifecycle change and the checks read only the state afterwards — the same state a no-op leaves when the subject was already there. Declare the change as a change: `created(subject=…)` / `removed(subject=…)`. |
| `undeclared-obligation` | warn | A node mints obligations and declares **no** check at all, so a QA plan claiming them can assert anything and still pass. Declare a check per observation; `ostler checks` lists the vocabulary. `field` nodes are exempt: they are observed through the record that carries them. |
| `competing-implementations` | warn | Two or more nodes of the same type — unrelated by containment or `extends:` — ground themselves in one `path::symbol`, and neither spelling of the selection rule is written down, so a reader reaching either cannot learn which to use or when. Write it centrally — one concept stating the rule ([node-types/concept.md](node-types/concept.md)) that every competitor points at with `detail:` — or distributively, where the members are states of one thing rather than rival implementations: every member naming every other under `exclusive-with:` **and** each stating the condition it holds under (`states:`/`when:`). Exclusivity alone says *not both*, never *which*, and clears nothing. A competition the source does not settle is recorded as a competition, not resolved by invention. |
| `deprecation-without-successor` | warn | A concept's `deprecates:` resolves but it carries no `prefers:` and no `rule:` — a deprecation with no successor reads as "delete this", which is usually wrong. Link the winning node with `prefers:`, or state the conditional answer as `rule:` prose. |
| `malformed-declaration` | error | A surface index carries `exercised:` with a value that is not a boolean. The declaration is either made or absent; a malformed one excuses nothing. |
| `stale-declaration` | error | `exercised: false` on a surface with no node under it — nothing is left to declare out of scope, and the next book written under that name would inherit the declaration unseen. Delete the key, or the index with it. |
| `ungrounded-unspecified` | error | An `unspecified:` bullet claims a behaviour is resolved by design, but no markdown link in it resolves to an existing record — nothing distinguishes it from a gap someone decorated. An error because the remedy is mechanical: cite the record that settled it (a decision doc, an acceptance criterion, a stated convention — see [bullet-grammar.md](bullet-grammar.md)), or delete the bullet. |
