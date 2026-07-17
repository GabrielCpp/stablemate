# Design: Make the okf-builder's completeness claim a computed fact

**Status:** §6 (multi-language front end + blindness guard) and **§4 (the instrument — Stage 1)**
are **implemented**. §5, §7–§11 are proposed. **§14 is the order of work**, and **Stage 0 has been
run** — its findings are recorded in the consuming repo (`docs/okf-stage0-findings.md`) and are
folded into §14 below.
**Scope:** make coverage *computable*, then let the machine — not an agent's self-report — decide
when a book is done; give the walk a session, a restorable fixture, and a verdict it can reopen;
define the per-service pipeline; document only what is missing or moved; support more than one book
per graph so two codebases can be compared by query instead of by judgement.
**Motivating scenario:** a rewrite — an old codebase and its replacement documented as two books in
one graph. Rewrite is the *scenario*, not the design: nothing below assumes a legacy mirror, a
second book, or a running app.

---

## 1. Problem

The builder's stop condition is `coverage_complete`, a value the `recheck` **agent emits about its
own work**. That looks like the bug. It isn't.

**The instrument is broken, and it reads tens of points low.** Measured against a real three-book
repo, a hand-built join said the largest book was 35% covered. Teaching that same join the *book's
own symbol grammar* moved it to 83% (+47 points) — without touching a single doc. Applying §4.3's
module rule on top takes it to 91% (+56):

| book | units | strict join | grammar-aware | recovered purely by grammar |
| ---- | ----: | ----------: | ------------: | --------------------------: |
| api  |   989 |  349 (35%)  |    817 (83%)  |                         468 |
| report | 221 |  153 (69%)  |    184 (83%)  |                          31 |
| web  |   374 |  238 (64%)  |    238 (64%)  |            0 (no receivers) |

> **Note.** Those books were deliberately cleared after this was measured; the numbers are
> historical. They are kept because they are the *evidence* for §4, and the instrument bug outlives
> the books it mismeasured — a rebuilt book will be mismeasured identically. See §12.

The cause is that the two sides of the diff speak different languages, in three independent ways:

**1.1 Symbol grammar.** `symbols()` emits bare identifiers (`SetRoleClaims`); books cite the
idiomatic receiver-qualified form (`(*FirebaseClaimsWriter).SetRoleClaims`). In the measured book,
**1136 citations are dot-qualified and 0 of the inventory's 877 symbols are** — those rows can
never match. Note which side is *better*: a bare name cannot disambiguate two types declaring the
same method in one file. **The book is right and the inventory is wrong.**

**1.2 The `module` unit is language-dependent, and the inventory treats it as universal.** The
measured books cite **0 bare file paths out of 1637** (api) and 0 of 515 (report): their convention
is to cite symbols, so a file-level unit is *uncitable by construction* — yet it sits in the
denominator. There are **282 uncited modules** (112 api / 133 web / 37 report), and **238** of them
— 86, 123 and 29 respectively — are **fully symbol-covered**: every symbol they declare is cited, so
the file adds nothing the book has not already said. But this is not simply a phantom to delete: for a
template language a file *renders a screen*, so the file is the real unit and its blocks are
secondary. The unit shape is language-shaped; only the consumer can resolve it (§4.3).

**1.3 Path convention.** Some books cite repo-root-relative (`api-service/internal/x.go::S`),
others service-relative (`app/routes/x.tsx::S`) — in the same tree, with nothing enforcing either.
`code` is declared `BulletKey("code", link=True)`, but `doctor`'s link validation only considers
`is_doc_link` (`.md`) targets, so code references are never checked for existence or shape.

**The honest conclusion: coverage today is not wrong, it is _undefined_.** Any number — including
one produced by a careful human — depends on which reconciliation heuristic the reader invents.
Strip the artifacts and the measured books' real gap is **107 units**, not the **844** a naive join
reports. The arithmetic — the first two rows from the table above, the rest from §1.2:

```text
844   strict-join misses          (640 api / 68 report / 136 web)
345   survive the grammar fix     (§1.1 — 499 were grammar artifacts)
238   discharged by the module rule (§4.3 — fully symbol-covered files)
107   real                        = 44 undischarged modules + 63 uncited symbols
                                    (63 splits api 60 / web 3 / report 0)
```

Note the 107, not 63. An earlier revision reported 63 by treating **all 282** uncited modules as
phantom — which is the "drop the module unit" rule this design **rejects** (§4.3), because a template
file is a real unit. Under the rule actually adopted, 44 modules stay honestly uncovered. The looser
number was more flattering and less true; it is exactly the kind of figure §4 exists to stop anyone
from inventing. A number nobody can reproduce is worthless whether it reads high or low; that, not
the agent's honesty, is what §4 fixes.

### The second failure family: success-shaped failure

Six places where the system reports "fine" without evidence:

**1.4 An unreadable language was indistinguishable from a documented one.** *(fixed — §6.)*
`inventory-source.py` filtered to `{.go,.py,.ts,.tsx}`. Pointed at a PHP/Twig tree of 274 source
files it emitted `source_unit_count: 0` with `inventory_errors: ""` — zero units, **zero errors**.
The recheck agent then correctly observes that every unit in an empty list is covered, and the run
declares the book complete having documented nothing.

**1.5 The gate's defaults are optimistic exactly where they claim to be safe.** The `recheck` node
defaults `coverage_complete` to `"no"` with a comment naming this the safe failure mode. The branch
that consumes it does not agree:

```yaml
- id: decide_coverage
  path: coverage_complete
  cases: {"yes": run_walkthrough_web, "no": seed_recheck}
  default: run_walkthrough_web        # any unrecognized value ⇒ "complete"
```

The output default protects against a *missing* key; the branch default surrenders on a *malformed*
one (`"Yes"`, `"true"`, `"partial"`). `decide_checkpoint` has the same shape.

**1.6 Giving up is indistinguishable from converging.** `guard_rounds` routes round ≥ 6 to `done`
— a `terminal`, exit 0. A run that exhausted its rounds reports success identically to one that
converged, and no durable artifact records which happened.

**1.7 The walkthrough fails open to "not a web app."** `detect-webapp` — the flow's *first* gate —
resolves everything from the book via `subprocess.run(["ostler", "search", …])` and swallows every
failure into `return []`. No ostler on PATH, a non-zero exit, or unparseable stdout all yield zero
screens ⇒ `is_webapp: "no"` ⇒ `gate_webapp` routes to `wt_done`: **a clean skip, exit 0, no walk,
no complaint.** `seed-walkthrough.py` and `checkpoint.py` share the pattern. This also violates the
library's own rule (`workflows/README.md`): *"External tools are libraries, not subprocesses… never
by shelling out to `git`/`gh`/`ostler` and scraping stdout."* It survives today only because
`ostler` happens to be an editable install on `PATH`; in a container it is a silent no-op.

**1.8 The walk's self-bootstrap works on the main path and fails silently off it.**
`detect-webapp.py` decides web-app-ness *from the book*:

```python
# 1) Web-app iff the book documents at least one `screen` surface for this service.
screens = [s for s in _search(root, "screen") if scope in s.get("path", "")]
if not screens:
    emit(is_webapp="no", ...)        # exits 0
```

On a full run this is **fine**, and it is worth being precise about why: `enumerate_surfaces` sits at
position 4 of the DAG and `run_walkthrough_web` at position 20. Screens are enumerated *from source*
(`prompts/enumerate-surfaces.md`: "top-level rendered views/templates, React Router route modules, or
TSX screen components → one `screen` per composed view") and documented by the drain loop long before
the walk is reached. A clean `docs/` is not a barrier: the static phase fills it first.

The defect is narrower, and it is a **fail-open on an unsupported invocation**. The flow advertises
itself as standalone —

> `workhorse run okf-builder walkthrough-web --params '{"service":"x"}'`

— and standalone against a book that has no screens yet, it exits 0 having done nothing. Same for the
launch recipe, read from the book's `server` node. The circularity is real but bounded; it does not
make "clean rebuild" and "walk the app" mutually exclusive. What it does is make one documented entry
point a no-op that reports success, which is §1.4's shape at a smaller scale.

**1.9 An unauthenticated crawl of an authenticated app succeeds.** The walk has no notion of a
session — `prompts/walkthrough-web.md` never mentions login, credentials, or state. Point it at an
app with a login wall and the crawl reaches it, documents that one screen, finds no onward links,
and **terminates normally**. A walk that saw one screen and a walk that saw the whole app are
indistinguishable in every artifact the run produces. This is §1.4 once more: absence of signal — no
session — rendered as a pass.

---

## 2. What already exists (and must not be rebuilt)

- **The drain loop, worklist, gas tank, and round caps work.** The build's *structure* is sound;
  this design changes what decides `done`, not how work is enumerated.
- **`prompts/recheck-coverage.md` already describes the correct diff** and already forbids
  sampling. Its instructions survive; only the *verdict* moves out of the agent.
- **`ostler graph --has-bullet code`** already lists the documented side. The join has a home.
- **`ostler vet`, the shared CDP browser, and the walk's boot/teardown lifecycle** are sound.
- **The per-service config seam.** `workflow.okfBuilder.services.<name>` already carries `source`
  and `excludes` per book. §7 extends it rather than inventing a parallel channel.

> An earlier revision listed *the books themselves* here, arguing a ~95% symbol-covered corpus must
> not be discarded to fix a measurement bug. That decision was made the other way and the books were
> cleared. What survives from the argument is its consequence, not its recommendation — see §12.

---

## 3. Design principles

1. **The machine computes coverage; the agent adjudicates ambiguity.** Whether `parseRequest` is
   folded into a documented endpoint's contract is a judgement. Whether it appears in the book is
   arithmetic. Only the first belongs to an agent, and its answer must be **recorded durably** so
   it is not re-litigated every round.
2. **When the book and the tool disagree about grammar, the book wins.** The book is written in the
   language's idiom by something reading real code. A tool that cannot parse it is the defect.
3. **Silence is never evidence.** An empty inventory, an unreadable language, an unavailable
   dependency, a gate that cannot reach its data — each must fail loudly. Every one of §1.4–§1.9 is
   the same bug: *absence of signal rendered as a pass.*
4. **Giving up must not look like success.** Exhausting a cap is a distinct, visible outcome.
5. **A unit's shape is language-shaped.** Symbols are the unit for Go/TS; the file is the unit for
   a template language. The inventory reports both and does not pretend one rule fits all.
6. **Capability is declared, not inferred.** Whether a service can be *walked*, and how to boot it,
   is config the repo states — never something sniffed from the artifact the run is about to produce.
   Absence of a declaration is a decision; failure to honour one is an error. Note the scope: config
   declares walkability, **not** whether screens exist. Screens come from source (§9); a service can
   document screens and still be non-walkable.
7. **The book is the walk's spec, never the walk's gate.** Reading the book to know *what to test*
   is the design (§9): the book states the screens, actions and transitions, and the walk confirms
   them. Reading the book to decide *whether to run at all* is the bug (§1.8, §7.1) — a gate whose
   input is the artifact the run produces cannot fail honestly on a tree where that artifact is
   missing. Spec from the book; capability from config.
8. **The base stays repo-agnostic.** Nothing here may assume a rewrite, a legacy mirror, a running
   app, or a second book. A single-book greenfield repo must benefit from §4–§10 and notice nothing
   from §11. Ports, URLs and launch commands live in the consuming repo's `agents.yml`, never in a
   base prompt or script.

---

## 4. The instrument — make coverage computable

Nothing downstream is trustworthy until the join works. This phase adds no agents.

**4.1 Adopt the book's grammar; do not invent one.**  ✅ IMPLEMENTED A `code:` target is
`<path-relative-to-repo-root>::<symbol>`, where `<symbol>` is qualified by its owner when it has
one. This is not a new convention — it is what the books already write, and it is strictly more
precise than a bare name. Specified in **`docs/okf-ui-profile.md` §5** ("The `code:` target
grammar"), beside the `code` bullet key — *not* `ostler/SPEC.md` as this section first said:
SPEC.md is the epic/story profile, and the `code` bullet is a UI-profile key.

> **One correction from implementing it.** The profile already grants a third form the design
> did not account for: `code:` may name a **`file` region** (`dashboard.html::notification
> permission bootstrap`) for an unnamed region of a non-code file — shipped, real usage. §4.4
> grounds the file but not the region, since prose is not a name. A first cut held regions to a
> symbol's bar and produced 9 false findings against stablemate's own books. Per §3.2 the book
> won and the tool was the defect.

**4.2 The inventory emits that grammar.**  ✅ IMPLEMENTED Go's `symbols()` gained receiver
qualification (both `(*T).Method` and `T.Method` appear in real books); paths are now
repo-root-relative (the inventory already carried `repoRoot`). PHP already did this (§6) — Go was
the outstanding case. Measured on the same `api` tree as §1: **506 of 877 symbols are now
receiver-qualified where 0 were**, and `(*FirebaseClaimsWriter).SetRoleClaims` — §1.1's own
example — now matches. Excludes stay source-relative (they are configured per service); only the
emitted unit is repo-rooted. One unrelated blindness bug surfaced and was fixed: a generic type
declaration (`type Stack[T any] struct{}`) matched no pattern and was silently dropped.

**4.3 `ostler coverage` — the join, in ostler, tested.**  ✅ IMPLEMENTED
`ostler coverage --surface <book> --inventory <path>` → `{covered, total, missing[]}`. It lives in
ostler, not a workflow script, because both the builder and a CI check need it and it deserves unit
tests over fixtures rather than a regex in a script node. It owns the **transitive module rule**:

> a `module` unit is covered if it is cited directly, **or** it declares at least one symbol and
> every symbol it declares is cited.

The `declares at least one symbol` clause is load-bearing and easy to omit. Without it the rule is
**vacuously true for a file that declares nothing** — and it would discharge exactly the case the
module unit exists for: a Twig template with no `{% block %}` renders a screen and must be cited
directly. The measured data shows this is not hypothetical. One book had **37 uncited modules and 0
uncited symbols**, yet only 29 were fully symbol-covered; the other 8 declare no symbols at all. A
vacuous rule marks those 8 covered on the strength of having found nothing in them, which is §3.3 in
miniature — silence read as evidence.

Measured effect on the deleted corpus: the rule discharges **238** of the 282 uncited modules
(§1.2), leaving **44** undischarged. Those 44 are of two kinds, and the distinction is the rule's
whole point: some declare symbols that are not all cited; **at least 15 declare no symbols at all**
(report's 8, plus ≥7 of web's 10 — web has only 3 uncited symbols to go round). The second kind is
the template case, and a vacuous rule would have marked every one of them covered. It does *not*
discharge all 282 — that would be the "drop the module unit" rule, which this design rejects because
a file is the real unit for a template language (§3.5).

**4.4 `doctor` validates `code:` targets.**  ✅ IMPLEMENTED A `code` bullet whose file does not
exist (`dangling-code-ref`), or whose symbol is absent from that file (`missing-code-symbol`), is
a finding. This is what stops two conventions from silently coexisting, what keeps the book honest
as the source moves under it, and — per §10 — what detects a documented unit that has since been
deleted. `verify:` stays deferred to the QA gate: its value is a test id as often as a
`path::symbol`, so it has no single shape to hold it to.

> **It found a real one on its first run — and the shape of it is the interesting part.** Against
> stablemate's own books, four citations read `farrier/farrier/install.py::_run_install` (and
> `_run_config`/`_run_source`/`_run_scaffold`). Those citations were **correct at `HEAD`**; an
> in-flight refactor splitting `install.py` into `cli.py` had moved every one of them, and the
> book had not followed. So this is not a book that rotted quietly over years — it is `doctor`
> catching the book lagging the working tree **within the same edit**, which is precisely the
> window §4.4 exists to close. `doctor` was green over all of it before. Fixed in the book.
>
> Note what this costs: `code:` grounding **couples doc authoring to code existing**, which is
> exactly why an earlier decision deferred it to a later QA gate. That reversal is deliberate —
> coverage is a join over these targets, and an unvalidated target is a join key nobody checked.
> The coupling is affordable because `code:` is not a required bullet: a doc written ahead of its
> code omits it until there is something to anchor.

---

## 5. The gate — make the verdict mechanical

**5.1 A `compute-coverage.py` script node replaces the self-report.** It calls `ostler coverage`
and emits `coverage_complete` plus `missing_count`. `decide_coverage` branches on *that*.

**5.2 The agent's role narrows and becomes durable.** `recheck` stops voting on completeness. It
receives the **computed missing list** and adjudicates only ambiguous rows — folded-in symbols,
deliberate non-units — writing each verdict with a reason to a committed `coverage-waivers` file
keyed by `code:` target. A waived unit counts as covered; an unwaived one does not. Waivers are
reviewable, diffable, and survive the round.

**5.3 Defaults become pessimistic.** `decide_coverage.default → seed_recheck`;
`decide_checkpoint.default → seed_fixup`. An unreadable verdict means "not done", matching the
intent already documented at the `recheck` node.

**5.4 Round exhaustion routes to a `fail` node, not `done`.** With 5.5, the failure names its own
number.

**5.5 The book records its own coverage.** `docs/features/<book>/coverage.json` —
`{covered, total, waived, screens, generated_from: {sourceRoot, excludes, commit}}`. Recording
`excludes` and the source commit matters three ways: coverage is meaningless without the exclude set
it was computed under; the artifact is what makes staleness visible to CI and to a reader; and the
`commit` is the anchor §10 diffs against. This file is load-bearing, not an audit trinket.

---

## 6. The front end — multi-language, and loud when blind  ✅ IMPLEMENTED

`inventory-source.py` now reads **Go, Python, TypeScript, PHP, and Twig** (`SOURCE_SUFFIXES`).

- **PHP** — classes, plus public methods qualified by their class (`AddProjectAction.getRenderPath`),
  from one source-ordered pass so the qualification tracks the enclosing class. Private/protected
  methods are not the documented surface; magic methods (`__construct`, …) are DI/framework
  boilerplate — both skipped, mirroring the `_`-prefix filter the Python front end already applies.
- **Twig** — the template *and* its `{% block %}`s (both whitespace-control forms). A template
  renders a screen, so the file is a real unit here (§3.5) — unlike Go/TS, where a file is a
  container.
- **Blindness is now an error.** A tree containing files but **none** the front end can read emits
  `inventory_errors` naming the extensions it could not read, instead of an empty inventory. A tree
  mixing readable and unreadable files is not blind — only a tree with no readable source is.

Regexes are adequate here for the same reason they are for Go: the inventory needs *the set of
declared names*, not a parse tree — and the guard converts a front end that under-reports from a
liar into a failure.

Measured effect on a Symfony/PHP+Twig codebase: **0 units → 1295** (259 modules + 1036 symbols).

---

## 7. The walkthrough — declared, not discovered

The walk has two independent defects: it cannot tell *"walked and found nothing"* from *"never ran"*
(§1.7), and its standalone entry point exits 0 having done nothing against a book whose screens are
not written yet (§1.8). Both dissolve by moving the walk's **capability and launch** inputs out of
the book and into config. Note the scope: only those. The walk's *spec* — which screens exist, what
they do, where they lead — stays in the book, because that is the whole design (§9, §3.7). Config
answers "may I run, and how do I boot"; the book answers "what am I checking".

**7.1 The launch contract is repo config.** Extend the `services` map the builder already reads:

```yaml
  okfBuilder:
    services:
      api-service:
        source: api-service
        excludes: ...
        # no `walk:` key → declared non-walkable. Not inferred, not sniffed. (Its book may still
        # document screens from source — walkability and screen-having are different claims.)
      web-app:
        source: web-app
        excludes: ...
        walk:
          url: http://127.0.0.1:5173
          launch: npm run dev
          cwd: web-app
          health: /
      legacy:
        source: legacy/app/website
        excludes: ...
        walk:
          url: http://127.0.0.1:8081
          launch: make -C api-service legacy-up
          cwd: .
```

This is where a URL belongs (§3.8): the consuming repo's `agents.yml`, not a base script and not a
node the run is about to write. Config is authoritative on a clean tree *and* on a built one — unlike
a `server` node's inferred `launch:`, which is an agent's guess at a boot command and boots the wrong
process when it guesses wrong.

**7.2 Walkability becomes a three-way outcome, and one of them is an error.**

| condition | outcome |
| --- | --- |
| no `walk:` key | **skip** — declared non-walkable; recorded, not silent |
| `walk:` present, app and browser come up | **walk** |
| `walk:` present, app or browser will not come up | **fail** — never a skip |

Note what is *absent* from that table: "screens found". Walkability is `walk:` present plus a target
that boots — nothing about the book's contents. A booted service whose book documents no screens is
a **conformance phase with an empty worklist**, which is a fact about the book (and §5's job to
judge), not a reason to declare the service screenless.

`is_webapp` stops being a *detection* and becomes a *lookup*. The fallback that synthesises a
Python/venv `serve` command from an older convention is deleted, not demoted: with the contract
declared, nothing needs guessing, and a guess that boots the wrong process is worse than an error.

**7.3 Use the in-process ostler API.** `detect-webapp.py`, `seed-walkthrough.py` and `checkpoint.py`
must import `Ostler` rather than shelling out (`workflows/README.md`; the
`stablemate-workhorse-scripting` skill). A read then raises on an unloadable graph instead of
returning `[]` — which is precisely the seam an in-process test fakes. After 7.1 the graph is no
longer consulted for *walkability*, but it is still read for the walk's worklist, and that read must
fail loudly.

**7.4 The CDP wiring is a precondition, and must be checked.** The walk boots one shared Chromium on
a fixed `--remote-debugging-port` so that the agent's Playwright MCP (`--cdp-endpoint`) and
`ostler vet --cdp-url` observe the same page. The port is fixed *because* the consuming repo's MCP
config is static — so a repo whose MCP is not pointed at that endpoint cannot be walked coherently.
`boot_browser` verifies the endpoint is reachable and that `ostler[vet]`'s extras (playwright,
pillow) are importable, and fails with that diagnosis rather than proceeding.

---

## 8. Walking a real app — session, fixture, and the mutation interlock

The walk was built and proven against a service with **no login, no data to create, and nothing to
break**. Every assumption in it reflects that, and two of them are wrong for any real app.

**8.1 The session is repo-declared, loaded by the base.** The base cannot know a login form's
selectors and must never carry credentials. Playwright's `storageState` is the seam:

```yaml
        walk:
          url: http://127.0.0.1:8081
          launch: make -C api-service legacy-up
          session:
            setup: make -C api-service walk-session   # repo's recipe; writes the state file
            state: .agents/walk/legacy.json           # base loads it into the browser context
```

The repo owns *how* to authenticate — a form post, an auth emulator's seed script, a token mint.
The base owns *load this state, and fail if it is missing*. Credentials reach the recipe through env
vars named in config and forwarded by `envPassthrough`, the pattern the repo already uses for its
CI token. No secret enters the tree.

**8.2 A post-login assertion, or the session is not proven.** `session:` declared and the entry URL
still redirecting to a login route ⇒ the walk **fails**. Without this, §1.9's silent pass returns
wearing a config key: a `session:` block that quietly failed to authenticate produces exactly the
one-screen "success" it was added to prevent. Declaring a capability is not evidence of having it.

**8.3 Mutation is gated by a fixture the walk can restore — not by prose.** The base today forbids
mutation in the prompt:

> *"Do not perform destructive actions. The app is a live boot. Do not click controls that delete,
> submit irreversible changes, or mutate real state… describe them in prose — do not trigger them."*

That rule is wrong in **both** directions, and prose cannot fix either. It blocks documenting the
create/edit/delete flows of a throwaway local DB — which is most of what an app *does*. And were it
loosened in prose, nothing would stop the same crawler deleting live records: a consuming repo's
config can legitimately point a fidelity/reference URL at **production**. Prose cannot tell those
two targets apart. Config can.

```yaml
          fixture:
            reset: make -C api-service testdb-reset   # drops the volume
            seed:  make -C api-service testdb-load    # reloads the dump
```

The interlock — every condition required:

| condition | mutation |
| --- | --- |
| no `fixture:` | **forbidden** — read-only walk; today's prose rule, now with a reason |
| `fixture:` present, `url` host is not loopback | **refused** — the run fails; not overridable |
| `fixture:` present, loopback, `reset` + `seed` run green | **permitted** |

**A crawl may only mutate a target it can prove it can restore, and the proof is executing the
restore.** You cannot `docker compose down -v` production. The loopback test is not belt-and-braces:
it is what keeps the proof honest, since a `reset:` recipe of `true` would otherwise "succeed"
against any host on earth. A repo's own capture skill may already draw this line by host — this
moves it from prose an agent reads into a gate the run cannot pass.

**8.4 Seed, don't mutate, wherever a fixture can carry the entity.** Most screens that "need data"
need it to *exist*, not to be *created*; a loaded dump reaches them with no mutation and no risk.
Reserve mutation for the flows whose screens **are** the mutation — the form, its validation errors,
the confirm dialog, the success state. That is a small set, and the only one worth the interlock.

**8.5 Native dialogs must be handled, not avoided.** A destructive control usually opens a
`confirm()`. An unhandled dialog blocks every subsequent browser event, and the walk hangs until its
node times out — surfacing, per §1.6, as an exhausted round rather than a stuck one. A mutating walk
registers a dialog handler before it clicks, or it deadlocks in a way the round cap will misreport.

---

## 9. The per-service pipeline — document, heal, walk

**The walk is a conformance test, not a crawl.** This is the single most important thing to get right
about it, and an earlier revision of this document got it wrong by proposing the walk as a discovery
front end that would enumerate screens from the running app.

It does not need to. By the time the walk runs, the book already states **what screens exist, what
actions each offers, and where each action leads** — all derived from source by `enumerate_surfaces`
and the drain loop. Route modules, templates, controllers and redirects are static text; a route table
is a better map of an app's surface than a crawler's link-following will ever be, because it includes
the routes a crawler cannot reach without knowing how.

So the walk has an **expectation** before it opens a page. That changes what it is:

```
the book (from source)  → the spec:  screens, actions, transitions
the running app         → the implementation
the walk                → the conformance test between them
```

Three consequences, each of which removes machinery rather than adding it:

- **Nothing needs to be guessed.** The walk does not hunt for clickable things; it checks the
  transitions the book claims. Mutation is bounded by the same fact — the walk triggers a delete
  because the book says a delete exists and says what it should do, not because a crawler found a
  red button.
- **A dialog is expected, not an ambush.** §8.5's `confirm()` hazard is documented behaviour the
  walk is testing, so the handler is registered because the spec called for it.
- **"Unverified" is a sharper axis than "undiscovered".** The gap that matters is not *screens
  reachable vs documented* — it is **screens documented vs screens confirmed against the app**.

What remains true from the epilogue critique is narrower but still real: `workflow.yaml:281` routes
`"yes": run_walkthrough_web` — the book is declared **complete**, and only then walked. The ordering
is right; the placement relative to the *verdict* is not. A conformance test whose failures cannot
reopen the verdict is a report nobody reads. The walk belongs after documentation and **before**
`done`, with its discrepancies re-entering the worklist and its verification status inside coverage.

One book per service. Each service runs the same pipeline; the `walk:` declaration decides which
stages are present:

| phase | non-walkable service (`api-service`, `report`) | walkable service (`web-app`, `legacy`) |
| --- | --- | --- |
| **A. boot** | — | `launch:` the app, boot the shared CDP browser; fail if either won't come up (§7.2) |
| **B. arm** | — | `fixture.reset` + `fixture.seed`; `session.setup` → load state; assert not on a login route (§8.2). Each step is a gate, not a best effort |
| **C. enumerate** | static inventory + `enumerate_surfaces` → units, incl. screens from route modules/templates | *(identical — screens come from source either way)* |
| **D. document** | drain loop: investigate → record; screens get their expected actions and `leads-to:` | *(identical)* |
| **E. heal** | checkpoint → fixup | *(identical)* |
| **F. conform** | — | walk each documented screen: confirm it renders, confirm each claimed transition, capture the screenshot, `ostler vet`. **Discrepancies re-enter the worklist** → D |
| **G. verify** | `ostler coverage` over symbols | `ostler coverage` over symbols **and** screen-conformance |
| **H. teardown** | — | teardown browser, teardown app |

Note what the table shows: **C, D and E are the same for every service.** A walkable service is not
a different pipeline — it is the same pipeline with an armed target (B) and a conformance phase (F).
That is the payoff of the walk knowing what to expect: the difference between `api-service` and
`legacy` is two phases at the edges, not a parallel architecture.

Phase **B** is what separates a real app from the read-only service this walk was proven against, and
it is the only phase whose failure must never be recoverable: an unarmed walk that proceeds is
precisely §1.9, and a mutating walk that proceeds without a verified-restorable fixture is worse than
a failed run.

Phase **G** is the only exit. It is mechanical (§5), it routes to `fail` on round exhaustion (§5.4),
and for a walkable service it carries a second axis it cannot fake: **screens documented vs screens
confirmed.** A book that documented every screen from source and confirmed none of them against the
running app is exactly the book §1.9 produces, and this is the number that says so.

One property worth stating: **the app boots once, in A, and stays up through F.** Arming a fixture
and loading a session are expensive; a conformance phase that re-boots per screen would pay that cost
per unit for no gain.

---

## 10. Delta builds — document only what is missing or moved

A second run over a built book must not re-document 1,300 units to change nine. The delta is
**derived, not stored** (§12) — computed from `coverage.json` plus the source tree, with no new
state and no per-unit bookkeeping.

**10.1 The full build is the delta from nothing.** Seed the worklist with `inventory − book` and both
modes collapse into one code path: on an empty `docs/` that difference is everything; on a built
book it is the gap. There is no `--mode` flag, because there is no second behaviour. The reason the
builder cannot do this today is not a missing feature — it is that `− book` is not computable until
§4 lands. **The instrument that makes coverage measurable is the same instrument that makes
incremental builds possible.** One fix, two capabilities.

**10.2 Three sets, three sources.** Given `coverage.json.generated_from.commit` as the anchor:

| set | how it is computed | disposition |
| --- | --- | --- |
| **new** | in inventory, not cited by the book | document it |
| **moved** | cited by the book, and its file changed between the anchor commit and `HEAD` | re-queue for heal — *cited ≠ accurate* |
| **gone** | cited by the book, absent from the source | §4.4 finding → prune the citation |

Only **moved** needs machinery the rest of this design does not already provide: a git diff of
`sourceRoot` between the anchored commit and `HEAD`, mapping changed files to the units they
declare. `workhorse.scriptutil.open_repo` is the seam; no shelling out to `git` (§7.3).

**10.3 The live axis deltas the same way, without git.** A screen's identity is its route, not a
file, and a route can change with no legible file-level diff — so screens are compared by set
arithmetic against the live app rather than against a commit:

| set | meaning | disposition |
| --- | --- | --- |
| **unconfirmed** | documented from source, never conformed against the app | walk it |
| **drifted** | documented, renders or transitions differently than claimed | re-document (phase D) |
| **unreachable** | documented from source, the walk could not get there | flag — never auto-prune |

**Unreachable is deliberately a flag.** A screen the walk could not reach is ambiguous: the route may
be dead, or the walk may have failed to log in, or the path to it may run through a state the fixture
does not carry. Deleting documentation on the strength of a failed walk is §3.3 inverted — treating
absence of signal as evidence of *absence*, the same error in the other direction. **The source says
the screen exists; the walk only ever proves it was confirmed, never that it is gone.** When those
two disagree, the source is the stronger witness and the walk is the one making a claim it cannot
substantiate.

**10.4 A mutating walk is only repeatable across a fixture reset.** The *documented* screen set is
stable — it comes from source (§9), not from the walk. What is not stable is **confirmability**: a
screen the book derives from a route module may need an entity to exist before it will render. A walk
permitted to create and delete data (§8.3) moves that state underneath itself — the screen confirmed
in run 1 *because the walk made the record* is unreachable in run 2, and gets flagged for no reason
but the walk's own history. Running `fixture.reset` + `fixture.seed` before each walk restores the
invariant: the confirmable set becomes a function of the fixture rather than of what the last run
happened to do. It costs a dump load per walk, and that is the price of a conformance result that
means anything. **The fixture is not only the mutation interlock; it is what makes the live axis
measurable at all.**

**10.5 A delta run is anchored or it is a full run.** No `coverage.json`, an unparseable one, or one
whose `excludes`/`sourceRoot` no longer match the config means the anchor is invalid — the run
rebuilds fully and says so. A stale anchor silently trusted would under-document exactly the units
that changed most.

---

## 11. Multi-book graphs and a computable difference

**The blocker is vocabulary, not tooling.** Measured on a real rewrite repo, the old-side docs are
100% `type: feature` and the new-side book is 0% `type: feature` (160 `concept`, 94 `format`, 48
`screen`, 17 `flow`, …). **The two books share no node type.** That is the whole reason the
difference has to be guessed, and no comparison machinery fixes it. Give both books one surface
spine and the difference becomes `ostler graph` set arithmetic.

The builder already takes `service` + `source_path` and writes `docs/features/<service>`, so a
second book costs **no new machinery** — it is another invocation. What §11 adds:

- **A surface spine both books populate**, so `screen`/`feature` nodes are commensurable and a
  missing surface is a set difference.
- **`ostler coverage --against <book>`**: surfaces in book A absent from book B.

**§6 and §9 are what make this real, and not in the way an earlier revision claimed.** The spine does
not come from *walking* two apps — screens are enumerated from **source** in both books, by the same
`enumerate_surfaces` vocabulary (§9). That is precisely why it works: a Twig template and a React
Router route module both reduce to a `screen` node, so the two books are commensurable before either
app is booted. §6 is what lets the template side be read at all; the walk's contribution is
**confirmation**, not vocabulary.

That ordering matters for §14: the difference between old and new is computable from two *documented*
books, and the walk raises confidence in each rather than producing the comparison. This is the
capability the retired `gaps:` field was approximating by hand — a human writing down a difference
that then had to be owned and aged. Enumerate both books and the difference is recomputed, never
stored.

**What this does and does not replace.** A book diff mechanically answers *"which surfaces exist in
A but not B"*. It does **not** answer *"this surface exists in both but behaves differently"*.
Divergence is a judgement about a **pair of documented surfaces** and remains agent work. The gain
is not that judgement disappears; it is that judgement gets a stable unit (a surface pair), two
comparable documents to ground in, and a result that is recomputable rather than stored state that
must be owned and aged.

Divergence findings are therefore **derived output** — recomputable from the two books — never
durable mutable records.

---

## 12. Out of scope / explicitly rejected

- **Rebuilding a book *before* §4 lands.** The earlier revision of this document rejected rebuilding
  outright: the instrument was broken, not the books. That call was made the other way and the corpus
  was cleared, so the recommendation is moot — but its *consequence* is now the binding constraint.
  A rebuild measured by today's join reproduces the same unmeasurable result on fresh docs, at full
  cost, and this time with no ~95%-covered corpus to fall back on. §4 was optional when the books
  existed. It is a precondition now.
- **Rewrite semantics in the base.** No node, script, or prompt may assume a legacy mirror, a
  fidelity source, or old-side evidence. Two books are a *graph* capability; "one of them is the old
  app" is the consuming repo's framing and belongs in a flavor. Likewise `walk:` is generic — a URL
  and a launch command — not a legacy-mirror feature.
- **Auto-pruning a screen the walk could not reach.** §10.3. The walk proves reachability, never
  non-existence.
- **Mutating a target the run did not boot.** A remote staging environment is a legitimate mutable
  target in principle, and §8.3 refuses it anyway. An escape hatch on a safety interlock is how
  interlocks die: the flag gets set once for a good reason, then outlives the reason. No autonomous
  documentation crawler needs to create records on a host it did not start. If the need is real it
  should arrive as a new declaration carrying its own proof of disposability — not as a boolean that
  disables this one.
- **Enumerating mutation journeys in config.** A declared list of "create project → view → delete"
  scripts would put the base in the business of knowing an app's flows — and would duplicate, by
  hand, what the book already states from source (§9). The book is the itinerary; config gates the
  blast radius (§8.3); the agent judges the ambiguous cases (§3.1). Three different jobs, and the
  one thing none of them needs is a fourth copy of the app's flows in YAML.
- **A tree-sitter/LSP front end.** Real symbol resolution would beat regexes, but it trades a large
  dependency for accuracy the coverage diff does not need. §6's guard converts the regex front end's
  failure mode from silence into an error, which is the property that actually matters.
- **Replacing the agent's judgement on folding.** Deciding that a helper is subsumed by a documented
  contract is genuinely a judgement. It is scoped and recorded (§5.2), not eliminated.
- **A durable per-finding record with an ownership lifecycle.** Prior art in this codebase shows the
  failure mode: findings whose disposition is only ever set at birth accumulate, go unowned, and
  drift from the code they describe, while the gate meant to catch that reads inputs that no longer
  exist. Derived-and-recomputed beats stored-and-maintained. §10 is built this way on purpose.

---

## 13. The lesson worth keeping

Every defect above is one bug wearing seven coats: **absence of signal rendered as a pass.** An
unreadable language returns no units → "covered". An unreachable graph returns no screens → "not a
web app". A standalone walk against a not-yet-written book returns no screens → exit 0, having done
nothing. No session returns one screen → "walked". A malformed verdict hits an optimistic branch
default → "complete". An exhausted round cap routes to a terminal → exit 0. A grammar mismatch
returns no join → "uncovered" (the same bug inverted — and the one whose 35% reading was cited in
favour of clearing a book that was really at 91%).

The rule that would have caught all seven: **a gate may only report a pass it can show its work
for.** Anything else is an error.

Note what the interlock in §8.3 does with that rule. It does not ask the run to *promise* the target
is disposable — a promise is a self-report, and this document is a catalogue of what those are worth.
It asks the run to *restore* the target, and treats success at that as the evidence. The permission
to destroy data is granted by the demonstrated ability to put it back.

This applies to the harness as much as to the workflow. Claude Code's `/goal <condition>` sets a
condition **checked before stopping** — so the condition is itself a gate, and it inherits the disease
by default. Phrase it as prose —

```
/goal the OKF books are complete and accurate
```

— and it is judged by the same self-assessment this document exists to remove, now sitting at the
outermost loop where nothing checks it. Phrase it as a predicate:

```
/goal make okf-verify exits 0
```

and the stop condition is something the run can be held to. `okf-verify` starts nearly empty and
gains one assertion per stage below: coverage per book (§4–§5), screens confirmed vs documented (§9),
the walk armed rather than skipped (§8). That is what §4 and §5 are ultimately for — not a number for
a report, but a predicate that can refuse.

Which is also why §14 puts the gate before the books: **the goal cannot be written until the thing it
checks exists.**

---

## 14. The path — order of work, and what each step buys

The stages below are ordered by **dependency, then by information gained per unit of effort**. Each
one ends at a checkable state, because a stage that cannot be checked is a stage that will be
reported complete (§13).

### Stage 0 — Run it and watch it fail *(no code)*  ✅ DONE

Point the builder at the smallest book on the now-empty tree and see what actually happens.

- **Why first:** every stage below is an inference from reading code. This is the only step that
  produces observations. It costs one run and it will correct at least one thing in this document —
  the prior two revisions each contained a confident claim that a five-minute check refuted.
- **Exit:** a written list of what broke, in what order, with the run's own output as evidence.
- **Explicitly not:** fixing anything. Resist. The list is the deliverable.

**It did its job — it corrected four things.** The full list lives in the consuming repo's
`docs/okf-stage0-findings.md`; what it changes *here*:

- **The install is the first blocker, not §4.** A base-library workflow's script nodes
  `from ostler import Ostler`, so ostler must be importable from *workhorse's* interpreter. The
  root README's "isolated tools" setup (three pipx venvs) cannot satisfy that, and no
  configuration can: `STABLEMATE_BASE_DIR`/`set-base` make the base *discoverable*, never
  ostler *importable*. That setup and `workflows/README.md`'s "external tools are libraries, not
  subprocesses" rule are mutually exclusive. One env (`pipx install stablemate-library
  --include-deps`) clears it with nothing configured.
- **§5.4 is understated.** "Round exhaustion routes to a `fail` node, not `done`" reads like one
  missing edge. There is **no failure exit at all**: `check_ostler: "no"`, `guard_budget: "yes"`,
  `guard_rounds: >=6` and `decide_coverage` all terminate at `done`. The gate is not one edge, it
  is the absence of a verdict.
- **Empty is indistinguishable from complete, and §5 never says so.** `doctor` is green on a book
  that does not exist — referential integrity over zero nodes is vacuously perfect. That is an
  argument for §5.5's `coverage.json` (0/221 answers it) which this document did not make.
  *(§4.3's `is_complete` now refuses a pass over zero units for the same reason.)*
- **A bug §14 was not looking for.** `prepare.py` reuses a worklist that outlives the book it
  remembers, and `select-item.py` computes `done` over the whole file — so `max_items` is a
  **lifetime** cap, not a per-run one. A deleted book's stale counter made a bounded run
  instantly over-budget and hand out zero items. Fold into Stage 2.
- **`prepare.py`'s fail-soft guard is dead code.** `from ostler import Ostler` sits at module
  scope, so the script dies with a traceback before `main()` can emit `ostler_ok="no"` — the
  `check_ostler` branch cannot fire for the one condition it is named after.

### Stage 1 — §4, the instrument  ✅ DONE

Delivered: Go receiver qualification + repo-root-relative paths (§4.2); `ostler coverage` with the
transitive module rule, waivers, and a non-zero exit on an incomplete book (§4.3); `doctor`
grounding `code:` targets (§4.4); the grammar specified in the UI profile (§4.1). 31 new tests.

**Exit met.** Against stablemate's own `workhorse` book: `ostler coverage --surface workhorse
--inventory <inv>` prints `52/135 units covered (38%)` and exits 1. Two findings from doing it:

- **The join surfaced a Python-side analogue of §1.1 that this document did not predict.** 53 of
  the workhorse book's 97 citations name `_`-prefixed symbols (`main.py::_run_run`,
  `_GasTank`, `_step_loop`) and module constants (`REGISTRY`) that the Python front end filters
  out of the inventory by design (§6 mirrors it in PHP's private/protected skip). These are not
  phantom misses — they cost nothing, because the units are not in the denominator. But it means
  **the book's notion of a unit is wider than the inventory's**: for an application (as opposed
  to a library) `_run_run` *is* the subcommand handler, a real behavioral unit. §3.5 says a
  unit's shape is language-shaped; this says it is also **application-shaped**.

  **Decided: leave it.** The `_`-prefix filter stays, and a book may over-document. The
  asymmetry is safe in the direction it actually runs — a citation outside the denominator
  costs nothing, whereas widening the denominator would change what "complete" means and make
  every existing book instantly less complete. Note this is *not* an instance of §3.2: the book
  and the tool do not disagree about **grammar** here, they disagree about **scope**, and a
  narrower denominator cannot render silence as a pass. Revisit only if a real build shows the
  narrow denominator letting a book under-document — the tell would be a symbol nothing cites
  and nothing queues, not a citation with no matching unit.
- **§4.4 found real drift immediately** (see the note there).

Go receiver qualification in `symbols()`; repo-root-relative paths; `ostler coverage` with the
transitive module rule; `doctor` validating `code:` targets. Unit-tested over fixtures.

- **Why here:** nothing downstream is measurable without it, including whether Stage 0's failures
  were real. It is also the precondition for §10 — the same join that computes coverage computes the
  delta, so this is one build for two capabilities.
- **Exit:** `ostler coverage --surface docs/features/<book>` prints a number that a second person
  can reproduce.

### Stage 2 — §5, the gate, and `make okf-verify`  ← NEXT

`compute-coverage.py`; pessimistic branch defaults; round exhaustion → `fail`; `coverage.json`.
Fold the whole bar into one target.

**Stage 0 adds three items to this stage that §5 did not have:**

- **Give the workflow a failure exit at all.** Not one edge — `check_ostler: "no"`,
  `guard_budget: "yes"`, `guard_rounds: >=6` and `decide_coverage` every one of them ends at
  `done` today. §5.4 reads like a refinement; it is the whole verdict.
- **Key the worklist to the book it remembers, and make `max_items` per-run.** `prepare.py`
  reuses a worklist that outlived a deleted book, and `select-item.py` counts `done` over the
  whole file, so a stale counter makes a bounded run instantly over-budget and hand out zero
  items. This is a correctness bug in the resume path, not a nicety.
- **Let `prepare.py`'s fail-soft guard fire.** Move `from ostler import Ostler` off module
  scope so `check_ostler` can emit `ostler_ok="no"` instead of dying with a traceback before
  `main()` runs.

**Not blocking, but it will bite whoever runs this next:** a base-library workflow's script
nodes import ostler, so the toolchain must be **one env** — the root README's isolated-tools
setup cannot run this workflow and no configuration can fix it. Either the README stops offering
it as an equal for base-library workflows, or that setup grows a way to make ostler importable.

- **Why here:** this is the step that makes a `/goal` writable. Until `make okf-verify` exists and
  can exit non-zero, any goal condition is prose judged by self-assessment — the very thing this
  document exists to remove, relocated to the outermost loop.
- **Exit:** `make okf-verify` exits non-zero on an incomplete book and zero on a complete one, and
  you can state which book is which without opening either.

### Stage 3 — Build the two non-walkable books

`api-service` and `report`. No walk, no session, no fixture, no browser.

- **Why here:** it exercises the entire static pipeline — enumerate → document → heal → verify — on a
  clean tree with a working instrument, and it does so with none of §7/§8's machinery in the way. If
  a book cannot be built and verified without a browser, no amount of walk hardening will help.
- **Exit:** two books green under `make okf-verify`. **This is the first point at which the workflow
  is genuinely workable**, for the services that need no app.

### Stage 4 — §7, the declared launch contract

`walk:` in config; the three-way outcome; the in-process ostler API; the CDP precondition.

- **Exit:** `api-service` (no `walk:`) records a declared skip; `legacy` and `web-app` boot.

### Stage 5 — §8, session and the fixture interlock

`storageState` load; the post-login assertion; `reset` + `seed`; the loopback refusal.

- **Why after 4:** the interlock is meaningless until something can boot the target it protects.
- **Exit:** the walk authenticates, and a mutating walk refuses to start against a non-loopback host.
  Test that refusal deliberately — an interlock nobody has seen fire is an assumption.

### Stage 6 — The `legacy` book, walked

- **Why this one before `web-app`:** it is the best walk target available and the reasons compound.
  It is **frozen**, so it is a one-time build that cannot rot underneath the work. Its screens are
  Twig templates, so the source→screen mapping is 1:1 and §6 already reads it. Its fixture is a
  loaded dump with real entities, so §8.4 applies at full strength — most screens need no mutation at
  all. And it is the book whose absence blocks §11.
- **Exit:** `legacy` green under `make okf-verify`, including the screen-conformance axis.

### Stage 7 — The `web-app` book, walked

The live app, an auth emulator session, and a fixture that moves. Everything Stage 6 proved, minus
every simplification Stage 6 enjoyed.

### Stage 8 — §11, the difference

Surface spine; `ostler coverage --against <book>`.

- **Why last:** it is the only stage that requires two finished books, and it is the one the retired
  `gaps:` field was standing in for. It is also the payoff: the difference between old and new stops
  being a thing someone writes down and starts being a thing the graph computes.

### What this ordering assumes

That **Stage 0 changes it.** The sequence above is derived from reading the code, and this document's
history is a record of how reliably that produces confident, wrong claims — a coverage figure that
was an artifact of my own join, a bootstrap paradox that the DAG's own ordering already solved. Treat
Stages 1–8 as a hypothesis with a good prior, and Stage 0 as the first evidence that will revise it.
