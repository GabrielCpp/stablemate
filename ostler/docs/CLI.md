# The `ostler` command reference

Every verb the CLI exposes, with its real flags. The
[README](https://github.com/GabrielCpp/stablemate/blob/main/ostler/README.md) covers what
ostler is, how to install it, and the shortest path to a first epic; this file is the
exhaustive listing you come back to for a flag.

Ostler operates relative to the **current working directory** — roots default to
`<cwd>/docs/{milestones,epics,features,specs}` plus `docs/backlog.md`. Every read command accepts `--json`; every
mutating command allocates ids as needed and writes canonical markdown in place.

The commands fall into three surfaces that barely overlap:

| Surface | Verbs | What it operates on |
|---|---|---|
| **The planning graph** | `doctor` `trace` `list` `search` `query` `next-*` `create` `delete` `seed` `set-status` `unblock` `backlog` `milestone` `todo` `edit` `freeze` `path` | `docs/backlog.md`, `docs/milestones/`, `docs/epics/`, `docs/specs/` |
| **The feature graph** (UI profile) | `reach` `locators` `graph` `coverage` `scaffold` `fmt` `vet` | `docs/features/` — the node/edge book |
| **Verification** | `qa` `artifact` | a story's spec dir, and what a QA run produces |

## Global

```bash
ostler --version
ostler -C, --chdir DIR <command> …            # operate as if run from DIR
ostler --handles  <command> …                 # print ids as short handles
ostler --full-ids <command> …                 # print ids in full
```

An id is `<PREFIX>-<26-char ULID>`, which nobody retypes, so ostler abbreviates it git-style to a
**handle** — `<PREFIX>-<6+ chars>`, the shortest slice unambiguous among the ids in the repo.
Human-readable output prints handles by default and `--json` prints full ids: a person wants a
short token, a program wants the identity that never changes. The two flags override either
default.

Input is not modal. **A handle is accepted wherever a command takes an id** — `trace`, `query`,
`create story --covers`, `seed add`/`seed remove`, `backlog prune`, `freeze`/`unfreeze` — no matter
how the run prints, so a token copied out of one command goes straight into the next. Anything that
is not a handle (a slug, a doc path) passes through untouched.

A handle **lengthens** when a colliding id is later minted. It is a display and input form only:
what gets written into a document is always the full id.

## Inspect

```bash
ostler doctor [--epic SLUG] [--json] [--no-schema]
#   conformance + referential integrity; non-zero on an error-level finding.
#   --no-schema skips JSON Schema validation.
ostler trace <token>
#   walk the graph from any node — a seed id, story slug, surface or doc path.
```

## Retrieve

```bash
ostler list  --type ETYPE [--epic E] [--status S] [--json]
ostler search <query> [--type ETYPE] [--json]
ostler query stories-covering-seed|surfaces-referenced-by-story <arg> [--json]
ostler next-epic [--json]                     # next queued epic with unfinished work
ostler next-story <epic> [--json]             # next runnable story (deps satisfied, not done)
ostler path epic <epic> | path spec <slug> | path story <epic> <slug> | path branch <slug> [--epic]
```

Epic directories are numbered in creation order (`docs/epics/0001-checkout-flow/`), so ask
`path epic` rather than joining `docs/epics/<slug>` yourself. Every command below still takes the
bare slug — the number orders the listing, it is not the epic's identity.

`--type` accepts the planning types (`epic`, `story`, `feature`, `spec`,
`seed`), every UI-profile node type (`screen`, `cli`, `server`, `concept`, `format`, `flow`,
`runbook`, `environment`, `component`, `command`, `endpoint`, `interaction`, `invocation`,
`method`, `field`, `step`, `untyped`), and any kind a repo declared in its own template.

## Mutate

```bash
ostler create epic    <name> --title T [--prefix P] [--json]
ostler create milestone <name> --title T [--source-items id,id] [--prefix P] [--json]
ostler create backlog-item <text> [--section S] [--prefix P] [--json]
ostler create story   <epic> <slug> --title T [--covers a,b] [--depends a,b] [--prefix P] [--json]
ostler create feature <slug> --title T [--area A] [--route R] [--prefix P] [--json]
ostler create spec    <slug> <doc> [--title T] [--json]   # idempotent; retro-stamps free-form docs
ostler update story   <slug> --title T --covers a,b --depends a,b
ostler delete epic <name> | delete story <slug> | delete feature <slug>

ostler seed add <epic> <id> [--status S] [--summary …] [--surface …] \
                            [--legacy-surface …] [--backing …] [--prerequisites …] [--source-bullet …]
ostler seed remove <epic> <id>
ostler set-status <slug> <status>
ostler unblock <slug> | unblock --epic <name> | unblock --all   [--status S] [--json]

ostler backlog adopt [--path P]
ostler backlog add <id> <text> [--section S] | backlog prune <id> | backlog list [--json]
ostler milestone set-source-items <name> <id> [id ...]
ostler todo add <epic> [--front] | todo prune <epic> | todo reorder <e…> | todo list [--json]
```

`--depends` names sibling slugs inside the same epic, and lands in the story's own
`story.md` under `## Dependencies` — one `- Blocked by: <slug>` per blocker, or the bare
`(none)` when nothing blocks it. `epic.md` carries no dependency edge. `update story`
rewrites that section wholesale, so pass every blocker each time, or `(none)` to clear it.

`create … --json` returns `{"ok": true, "id": "<allocated-id>", "name": "<name-on-disk>",
"message": "…"}`. For `create epic` the `name` is the numbered directory that was written
(`0001-checkout-flow`) — read it back rather than assuming which number the epic got.

`unblock` clears the give-up stamps a coder run leaves behind — `QA give-up after N attempts …`,
`Docs blocked — needs manual review: …`, `Blocked` — and restores `Not started` (or `--status S`).
Newer coder runs no longer write those stamps — a give-up ends the run instead — but stories
stamped by older runs still carry them. It exists because
that stamp is a *sentence*, it lands in both the frontmatter and the body bullet of every
`story.md`, and one run stamps several stories at once. A story whose status is not in that
vocabulary is never rewritten, so a `QA passed` story survives `--all` and a second run is a
no-op that still exits 0. Note what it does *not* change: a blocked story was already eligible
for selection — `next-story` only skips *done* work — so unblocking is about the label the next
agent reads, not about the queue. The per-run skip lists (`blocked-epics.txt`,
`qa-skip-stories.txt`) live in the workflow's run dir and are not ostler's to clear; a fresh run
drops them on its own.

`update story` replaces the title, seed coverage and sibling dependencies stored in the parent
`epic.md`. All three options are required so the command expresses one complete metadata state.
It preserves the story id, `story.md` bytes, status, optional metadata and subsection prose.
`delete epic` removes the numbered epic directory and its references from every milestone and the
legacy todo queue; numbering gaps are preserved.

`create backlog-item` is the normal entry point for new intake: it allocates and persists a full
id. `backlog add` remains available when importing an externally assigned id. `backlog adopt`
allocates ids for every unnamed bullet while preserving prose and nesting; it is idempotent. Every
bullet in a backlog is therefore an item. Write supporting context or non-item details as prose, not
as list items. `backlog prune` refuses a parent while it still contains nested items.

`create milestone` allocates an id independent of the readable `<name>` used for its filename and
records full backlog ids in `sourceItems`. `milestone set-source-items` replaces that ownership set
on an existing milestone and accepts full ids or unambiguous short handles. `doctor` reports an
error if one backlog id is owned by more than one milestone.

## Repair and approve

`edit` is **dry-run unless `--write`** — it prints the plan it would apply, which is what
makes a rename across a whole graph reviewable before it happens.

```bash
ostler edit relink        <old-path> <new-path> [--write]
ostler edit rename        <old-slug> <new-slug> [--write]
ostler edit settle-review <slug> [--write]
#   flip a story's status from its review-resolution.json, gated on the artifacts
#   and assertions the verdict cites.

ostler freeze   <ident> [--by WHO] [--note …]   # pin an approved story/seed as ground truth
ostler unfreeze <ident>
```

## Template-declared kinds

Once a repo declares its own hierarchy in `.agents/templates.yml`, the same four generic
verbs work against instances of any kind it declared:

```bash
ostler template new  <name> [kind ...] [--json]      # declare a template, optionally stubbing kinds
ostler template edit <name> --set <kind>.<field>[.<subfield>]=<value>
ostler template find [<name>] [--json]
ostler template delete <name>
ostler template apply  <name>                        # mkdir -p each doc_root + inject CLAUDE.md guidance

ostler new    <kind> <name> [key=value ...] [--json]  # <parent-kind>=<name> scopes nesting
ostler find   <kind> [<name>] [--json]
ostler set    <kind> <name> key=value [key=value ...] [--json]
ostler remove <kind> <name> [--json]
```

The schema, a worked 3-level nesting example, and the bundle-vs-leaf shape rules are in
[SPEC.md §9](https://github.com/GabrielCpp/stablemate/blob/main/ostler/SPEC.md#9-templates-and-template-declared-kinds).

## The feature graph (UI profile)

These operate on `docs/features/` — the typed node/edge book describing a product's
surfaces, not the epic/story planning graph. `--surface` scopes any of them to one service
subtree (`docs/features/<surface>`).

```bash
ostler graph [--surface S] [--type T] [--title T] [--path 'concept:agent / field:timeout'] \
             [--under ID] [--depth N] [--has-bullet KEY] [--bullet KEY=VAL] \
             [--links-to ID] [--orphans] [--tree | --ids | --json]
#   query the node/edge/bullet graph. --tree is the default; --orphans finds nodes
#   no edge points to. In --path, `/` means descendant and `>` means direct child.

ostler reach --from ID [target] [--surface S] [--json]
#   derive the documented click-path from one screen to another. Omit `target` to
#   audit every screen on the surface for reachability.

ostler locators [screen] [--surface S] [--json]
#   the Playwright locator for every documented control, and where it is ambiguous.

ostler coverage --inventory PATH [--surface S] [--waivers PATH] [--json]
#   join the book's `code:` citations against a source inventory; reports
#   {covered, total, waived, missing}. A waived unit counts as covered.

ostler scaffold <type> <name> [--service SVC] [--in FILE] [--title T] [--json]
#   create a node in the right place. File-level types take --service; section-level
#   types take --in, the surface doc to insert the `### id` into.

ostler fmt [paths ...] [--check]
#   canonicalize frontmatter, bullets and headings. --check writes nothing and
#   exits 1 if any file is not already canonical — the CI form.

ostler vet <screenshot> --manifest M (--cdp-url URL | --regions FILE) --slug S \
           [--state STATE] [--iou-threshold F] [--json] [--write]
#   deterministic visual-fidelity check of a rendered screen against the book.
```

The vet contract is documented in
[docs/VET.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/VET.md).

## Verification control plane

`ostler qa` owns the bookkeeping for a QA run: what the change obliges you to verify, then
the plan, then the ledger of what actually happened.

**Scope.** `qa context` builds and validates a deterministic base/head impact and obligation
scope for one story, and `context-validate` re-checks a scope already on disk:

```bash
ostler qa context --base <rev> [--head WORKTREE] --spec docs/specs/<story> \
  [--features-root PATH] [--source-root SURFACE=PATH] [--story-file PATH] [--json]
ostler qa context-validate --spec docs/specs/<story> [--json]
```

`--source-root` associates a production source root with an OKF surface and is repeatable —
that mapping is what turns a diff into a set of obligations.

Two kinds of changed file are dropped from that scope rather than turned into obligations.
**Scaffolding** — build files, dependency manifests, tooling and infrastructure config — never
runs and carries no user-observable behaviour. **Generated code** does run, but no person wrote
it: files under `mocks/`, `__mocks__/`, `generated/`, `vendor/` or `node_modules/`, names like
`*.gen.go`, `*.pb.go`, `*_pb2.py`, `*.g.dart`, `*.freezed.dart`, and anything carrying the
canonical `Code generated … DO NOT EDIT` banner. Documenting either would mean writing
Concepts for a code generator's internal error types; the contract a generated file encodes
belongs to the thing it was generated from — the OpenAPI document, the proto, the mocked
interface — which is in the same diff as a real unit.

**Plans.** A version-2 plan declares command, Playwright and Maestro targets and maps every
scenario to acceptance-criterion and OKF obligation ids:

```bash
ostler qa validate <plan.yml> [--spec SPEC] [--json]
ostler qa run      <plan.yml> [--spec SPEC] [--stop-on-fail] [--scenario ID] [--out-dir LABEL] [--json]
ostler qa clean    --spec DIR [--yes] [--json]
```

Validation rejects unknown coverage, unsupported actions and locators, disposable pre-run
inputs, literal secrets, and coverage without a machine assertion. Each run starts with an
empty `qa/`, writes an append-only ledger and a content-hashed manifest, and returns
`passed`, `failed`, `blocked` or `invalid`. Browser and mobile targets record continuously
by default.

`--scenario` with `--out-dir` is the dry run an author uses while writing a plan. `--out-dir`
is a **label**, not a path: it always resolves to `<spec>/qa/<LABEL>/`, so a rehearsal lands
inside the one directory a repo ignores and cannot invent a tracked sibling. `qa clean`
removes the sibling roots the old layout already left behind — recursively, and never
`qa-inputs/`, which holds a plan's tracked fixtures.

**Sessions.** The step-by-step form, for a run driven interactively rather than from a plan:

```bash
ostler qa start  <run_id> --story S --spec SPEC [--env KEY=VALUE] [--daemon NAME:ARGV]
ostler qa step   --id ID --label L --mechanism {live,fixture} --cmd CMD --spec SPEC \
                 [--timeout N] [--capture KEY=$.path] [--out PATH] [--allow-fail]
ostler qa assert --id ID --label L --spec SPEC \
                 --check {cloudwatch_filter,event_present,field_equal,http_status,no_duplicate} \
                 [KEY=VALUE ...]
ostler qa stop   --spec SPEC        # kill daemons, write the session_stop summary
ostler qa report --spec SPEC        # render the action ledger for a human
ostler qa replay --spec SPEC
```

`--daemon NAME:ARGV` starts a background process for the session; append `:READY_URL` to poll
before advancing. `ARGV` is a program and its arguments, split the way a shell would split
quotes but never handed to one — `&&`, `|` and `$VAR` reach the program as literal arguments
and fail at `exec`. A daemon is therefore a server, not a command line, and
`--daemon api:"go test ./..."` cannot be smuggled in as one. The full run contract is in
[docs/QA-RUN.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/QA-RUN.md).

**Evidence.** After a run, `qa evidence-map` joins the obligation scope, the run ledger, the
artifact manifest and the published verdict into one row per obligation:

```bash
ostler qa evidence-map --spec docs/specs/<story> [--out-dir LABEL] \
  [--status {contradicted,unproven,uncovered,claimed-but-unasserted,insensitive,covered}] \
  [--out PATH] [--json]
```

Each row carries the scenarios that claimed the obligation, the passing assertions bound to
it, the checks its `verify:` bullets declared against the ones the run actually invoked, the
artifacts those scenarios produced, and a status:

| Status | Meaning | Whose defect |
| --- | --- | --- |
| `covered` | a passing assertion is bound to it, invoking every declared check | — |
| `claimed-but-unasserted` | a scenario claims it, but asserted nothing — or not the declared check | the QA plan |
| `uncovered` | no scenario claims it and no assertion is bound to it | the QA plan |
| `contradicted` | an assertion bound to it failed, or `qa-evidence.json` publishes a verdict the ledger does not hold | the product, or the artifact |
| `unproven` | the scenario that would have observed it did not run to completion | the QA plan |
| `insensitive` | every declared check passed and none of them could have failed | the book's `verify:` bullets |

`unproven` is the one that looks like `contradicted` and is not. An aborted scenario leaves a
failing record bound to every obligation it claimed, but the record is the harness's note that
the run stopped, not an observation of the product — and the usual cause is a defect in the
plan: a misspelled field, a timeout, a step that raised. Reading it as a disproof accuses
whatever tree was under it, a clean one included.

`insensitive` is the other one that is not what it looks like, from the other side: the row is
green everywhere a reader checks, and the checks it is green on are ones no observation of the
product could have reddened. It is decided by `qa sensitivity`, below, and the repair is a
`verify:` bullet that names what would be different if the claim were false.

```bash
ostler qa sensitivity [--node SUBSTR] [--json]
```

Every verifier is a pure function of what was observed, so each declared call is given a
witness observation that satisfies it and then a family of mutations — the field the claim
names missing or holding something else, a different route answering, the ledger the write was
supposed to leave alone moved, the refusal carrying the credential it may not. A call is
*sensitive* when at least one mutation turns it red, and the command exits non-zero when a
claim's every declared call survives all of them. Nothing is executed, nothing is booted, and
no run is needed: the question is about the declaration, not about this run of the product.

The exit status is `0` only when every obligation is `covered`, so a caller can gate on the
join without parsing it. A missing or malformed ledger is a refusal rather than a map full of
`uncovered`: the two are indistinguishable in the output, and the wrong one of them reads as
a finding about the QA plan when it is a finding about the arguments.

## Artifacts

Workflow artifacts (a plan, a review resolution, a QA outcome) are schema-checked against a
registered contract rather than trusted:

```bash
ostler artifact list [--json]                       # the registered kinds
ostler artifact scaffold <kind> --spec SPEC [--force]   # write the kind's skeleton
ostler artifact vet      <kind> --spec SPEC [--json]    # validate against its contract
```

The contracts themselves are in
[docs/ARTIFACT-CONTRACTS.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/ARTIFACT-CONTRACTS.md).
