# The `ostler` command reference

Every verb the CLI exposes, with its real flags. The
[README](https://github.com/GabrielCpp/stablemate/blob/main/ostler/README.md) covers what
ostler is, how to install it, and the shortest path to a first epic; this file is the
exhaustive listing you come back to for a flag.

Ostler operates relative to the **current working directory** — roots default to
`<cwd>/docs/{epics,knowledge,features,specs}`. Every read command accepts `--json`; every
mutating command allocates ids as needed and writes canonical markdown in place.

The commands fall into three surfaces that barely overlap:

| Surface | Verbs | What it operates on |
|---|---|---|
| **The planning graph** | `doctor` `trace` `list` `search` `query` `next-*` `create` `delete` `seed` `set-status` `backlog` `todo` `edit` `freeze` `path` | `docs/epics/`, `docs/knowledge/`, `docs/specs/` |
| **The feature graph** (UI profile) | `reach` `locators` `graph` `coverage` `scaffold` `fmt` `vet` | `docs/features/` — the node/edge book |
| **Verification** | `qa` `artifact` | a story's spec dir, and what a QA run produces |

## Global

```bash
ostler --version
ostler -C, --chdir DIR <command> …            # operate as if run from DIR
```

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
ostler path spec <slug> | path story <epic> <slug> | path branch <slug> [--epic]
```

`--type` accepts the planning types (`epic`, `story`, `knowledge`, `feature`, `spec`,
`seed`), every UI-profile node type (`screen`, `cli`, `server`, `concept`, `format`, `flow`,
`runbook`, `environment`, `component`, `command`, `endpoint`, `interaction`, `invocation`,
`method`, `field`, `step`, `untyped`), and any kind a repo declared in its own template.

## Mutate

```bash
ostler create epic    <name> --title T [--prefix P] [--json]
ostler create story   <epic> <slug> --title T [--covers a,b] [--depends a,b] [--prefix P] [--json]
ostler create feature <slug> --title T [--area A] [--route R] [--prefix P] [--json]
ostler create spec    <slug> <doc> [--title T] [--json]   # idempotent; retro-stamps free-form docs
ostler delete epic <name> | delete story <slug> | delete feature <slug>

ostler seed add <epic> <id> [--status S] [--summary …] [--surface …] \
                            [--legacy-surface …] [--backing …] [--prerequisites …] [--source-bullet …]
ostler seed remove <epic> <id>
ostler set-status <slug> <status>

ostler backlog add <id> <text> [--section S] | backlog prune <id> | backlog list [--json]
ostler todo add <epic> [--front] | todo prune <epic> | todo reorder <e…> | todo list [--json]
```

`create … --json` returns `{"ok": true, "id": "<allocated-id>", "message": "…"}`.

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
[SPEC.md §10](https://github.com/GabrielCpp/stablemate/blob/main/ostler/SPEC.md#10-templates-and-template-declared-kinds).

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

**Plans.** A version-2 plan declares command, Playwright and Maestro targets and maps every
scenario to acceptance-criterion and OKF obligation ids:

```bash
ostler qa validate <plan.yml> [--spec SPEC] [--json]
ostler qa run      <plan.yml> [--spec SPEC] [--stop-on-fail] [--json]
```

Validation rejects unknown coverage, unsupported actions and locators, disposable pre-run
inputs, literal secrets, and coverage without a machine assertion. Each run starts with an
empty `qa/`, writes an append-only ledger and a content-hashed manifest, and returns
`passed`, `failed`, `blocked` or `invalid`. Browser and mobile targets record continuously
by default.

**Sessions.** The step-by-step form, for a run driven interactively rather than from a plan:

```bash
ostler qa start  <run_id> --story S --spec SPEC [--env KEY=VALUE] [--daemon NAME:CMD]
ostler qa step   --id ID --label L --mechanism {live,synthetic,fixture} --cmd CMD --spec SPEC \
                 [--timeout N] [--capture KEY=$.path] [--out PATH] [--allow-fail]
ostler qa assert --id ID --label L --spec SPEC \
                 --check {cloudwatch_filter,event_present,field_equal,http_status,no_duplicate} \
                 [KEY=VALUE ...]
ostler qa stop   --spec SPEC        # kill daemons, write the session_stop summary
ostler qa report --spec SPEC        # render the action ledger for a human
ostler qa replay --spec SPEC
```

`--daemon NAME:CMD` starts a background process for the session; append `:READY_URL` to poll
before advancing. The full run contract is in
[docs/QA-RUN.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/QA-RUN.md),
and the design rationale in
[docs/plans/ostler-qa-verification.md](https://github.com/GabrielCpp/stablemate/blob/main/docs/plans/ostler-qa-verification.md).

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
