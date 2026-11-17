# The `ostler` command reference

Every verb the CLI exposes, with its real flags. The
[README](https://github.com/GabrielCpp/stablemate/blob/main/ostler/README.md) covers what
ostler is, how to install it, and the shortest path to a first epic; this file is the
exhaustive listing you come back to for a flag.

Ostler operates relative to the **current working directory** — roots default to
`<cwd>/docs/{milestones,epics,specs}`. Every read command accepts `--json`; every
mutating command allocates ids as needed and writes canonical markdown in place.

The commands fall into two surfaces that barely overlap:

| Surface | Verbs | What it operates on |
|---|---|---|
| **The planning graph** | `doctor` `list` `search` `query` `next-*` `create` `delete` `seed` `set-status` `unblock` `backlog` `milestone` `todo` `edit` `path` `vet` | `docs/milestones/`, and on the artifacts shelf `epics/`, `specs/`, `backlogs/` |
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

Input is not modal. **A handle is accepted wherever a command takes an id** — `query`,
`create story --covers`, `seed add`/`seed remove`, `backlog prune` — no matter
how the run prints, so a token copied out of one command goes straight into the next. Anything that
is not a handle (a slug, a doc path) passes through untouched.

A handle **lengthens** when a colliding id is later minted. It is a display and input form only:
what gets written into a document is always the full id.

## Inspect

```bash
ostler doctor [--epic EPIC | --milestone NAME] [--json] [--no-schema]
#   conformance + referential integrity; non-zero on an error-level finding.
#   --no-schema skips JSON Schema validation.
ostler layout apply
#   rename every epic and story folder on the shelf to its id, record each epic's slug,
#   repoint the queue; exit 1 names each folder it could not move.
```

## Retrieve

```bash
ostler list  --type ETYPE [--epic E] [--status S] [--json]
ostler search <query> [--type TYPE] [--root ROOT] [--limit N] [--match] [--json]
ostler index build [--json]
ostler query stories-covering-seed <arg> [--json]
ostler next-epic [--json]                     # next queued epic with unfinished work
ostler next-story <epic> [--json]             # next runnable story (deps satisfied, not done)
ostler path epic <epic> | path spec <story-id> | path story <story-id> | path branch <story-id> [--epic]
```

`search` ranks sections with BM25 across the current book and decisions, OR-ing the query's terms
with prefix and stemming matches. `--root` names epics, milestones, specs or the register, and
`--root all` reads every root. `index build` builds
or refreshes the store that backs it and reports the counts.

Epic directories are named by the epic's id (`<artifacts dir>/epics/<epic-id>/`), and a story's
folder by the story's id (`stories/<story-id>/`). Ask `path epic` rather than joining a path
yourself. Every command below takes the epic's id, its short handle or its slug.
`ostler layout apply` renames the folders of a shelf still in the numbered `NNNN-slug` layout.

A story is addressed by its id. The slug names the story's `### <slug>` heading in
`epic.md`, and no command looks a story up by it. A slug passed where an id belongs is refused, and
the error names the id to use.

`--type` accepts the planning types (`epic`, `story`, `milestone`, `spec`, `seed`) and any kind
a repo declared in its own template.

## Mutate

```bash
ostler create epic    <name> --title T [--json]
ostler create milestone <name> --title T [--source-items id,id] [--json]
ostler create backlog-item <text> [--section S] [--json]
ostler create story   <epic> <slug> --title T [--covers a,b] [--depends a,b] [--json]
ostler create spec    <story-id> <doc> [--title T] [--json]   # idempotent; retro-stamps free-form docs
ostler update story   <story-id> --title T --covers a,b --depends a,b
ostler delete epic <name> | delete story <story-id>

ostler seed add <epic> <id> [--status S] [--summary …] [--surface …] \
                            [--legacy-surface …] [--backing …] [--prerequisites …]
ostler seed remove <epic> <id>
ostler set-status <story-id> <status>
ostler unblock <story-id> | unblock --epic <name> | unblock --all   [--status S] [--json]

ostler backlog adopt --repo R <file> [--json]
ostler backlog add <summary> --repo R --area A [--pattern P] | backlog prune <id> | backlog list [--json]
ostler milestone set-source-items <name> <id> [id ...]
ostler milestone epics <name> [<epic> ...]
ostler todo add <epic> [--front] | todo prune <epic> | todo reorder <e…> | todo list [--json]
```

`--depends` names sibling slugs inside the same epic, and lands in the story's own
`story.md` under `## Dependencies` — one `- Blocked by: <slug>` per blocker, or the bare
`(none)` when nothing blocks it. `epic.md` carries no dependency edge. `update story`
rewrites that section wholesale, so pass every blocker each time, or `(none)` to clear it.

`create … --json` returns `{"ok": true, "id": "<allocated-id>", "name": "<name-on-disk>",
"message": "…"}`. For `create epic` the `name` is the directory that was written, which is the
epic's id.

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

`create backlog-item` is the normal entry point for new intake: it files one record on the
Register and persists a full id. `backlog add` does the same. `backlog adopt` turns an old bullet
list into records once and deletes the list. `backlog prune` closes a record as done, dropped or
promoted.

`create milestone` allocates an id independent of the readable `<name>`, writes the milestone to
`docs/milestones/NNNN-<name>/` with the next free number, and records full backlog ids in
`sourceItems`. The bare `<name>` still names the milestone in every command. `doctor` warns on a
milestone folder with no number and prints the `git mv` that numbers it.
`milestone set-source-items` replaces that ownership set on an existing milestone and accepts full
ids or unambiguous short handles. `doctor` reports an error if one backlog id is owned by more than
one milestone.

`milestone epics <name> <epic>...` sets the milestone's epics in coding order. It takes each epic
by id, folder or slug, stores the ids under `epics:`, and writes the `## Epics` section under the
milestone's title: one line per epic with its title and id. With no epic it resolves the
list the milestone already holds, which moves a list written by name onto ids. Once the milestone
is `approved`, `doctor` reports an epic listed by name and an `## Epics` section that is not the
list as errors.

`doctor --milestone <name>` checks one milestone, the epics it lists and their stories, and exits 1
on any error. Beyond the graph checks it refuses an epic or story with no `id:`, an epic folder with
no `epic.md`, an epic with stories whose `epic.md` lacks `## User Outcome`, `## User Journeys`,
`## Delivered Experience`, `## Guardrails`, `## Non-Goals`, `## Acceptance` or `## Method`, and a
story that covers no seed outside a follow-ups epic.

## Repair and approve

`edit` is **dry-run unless `--write`** — it prints the plan it would apply, which is what
makes a rename across a whole graph reviewable before it happens.

```bash
ostler edit relink        <old-path> <new-path> [--write]
ostler edit rename        <old-slug> <new-slug> [--write]
ostler edit settle-review <story-id> [--write]
#   flip a story's status from its review-resolution.json, gated on the artifacts
#   and assertions the verdict cites.
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

## Verification control plane

`ostler qa` owns the bookkeeping for a QA run: the plan, then the ledger of what actually
happened.

**Plans.** A plan declares command, Playwright and Maestro targets and maps every
scenario to the ids it covers:

```bash
ostler qa validate <qa_plan.py> [--spec SPEC] [--json]
ostler qa run      <qa_plan.py> [--spec SPEC] [--stop-on-fail] [--scenario ID] [--out-dir LABEL] [--json]
ostler qa clean    --spec DIR [--yes] [--json]
```

Validation rejects unsupported actions and locators, disposable pre-run
inputs, literal secrets, and coverage without a machine assertion. Each run starts with an
empty `qa/`, writes an append-only ledger and a content-hashed manifest, and returns
`passed`, `failed`, `blocked` or `invalid`. Browser and mobile targets record continuously
by default.

`--scenario` with `--out-dir` is the dry run an author uses while writing a plan. `--out-dir`
is a **label**, not a path: it always resolves to `<spec>/qa/<LABEL>/`, so a rehearsal lands
inside the one directory a repo ignores and cannot invent a tracked sibling. `qa clean`
removes generated QA output recursively and never `qa-inputs/`, which holds a plan's
tracked fixtures.

**Sessions.** The step-by-step form, for a run driven interactively rather than from a plan:

```bash
ostler qa start  <run_id> --story S --spec SPEC [--env KEY=VALUE] [--daemon NAME:ARGV]
ostler qa step   --id ID --label L --mechanism {live,fixture} --cmd CMD --spec SPEC \
                 [--timeout N] [--capture KEY=$.path] [--out PATH] [--allow-fail]
ostler qa assert --id ID --label L --spec SPEC \
                 --check {cloudwatch_filter,event_present,field_equal,http_status,no_duplicate} \
                 [KEY=VALUE ...]
ostler qa stop   --spec SPEC        # kill daemons, write the session_stop summary
ostler qa report --spec SPEC [--out-dir LABEL] [--ledger]   # render qa-report.md for a human
ostler qa frames --spec SPEC (--step ID | --at SECONDS [--target T]) [--around S] [--fps N] [--out-dir LABEL]
ostler qa replay --spec SPEC
```

`--daemon NAME:ARGV` starts a background process for the session; append `:READY_URL` to poll
before advancing. `ARGV` is a program and its arguments, split the way a shell would split
quotes but never handed to one — `&&`, `|` and `$VAR` reach the program as literal arguments
and fail at `exec`. A daemon is therefore a server, not a command line, and
`--daemon api:"go test ./..."` cannot be smuggled in as one. The full run contract is in
[docs/QA-RUN.md](https://github.com/GabrielCpp/stablemate/blob/main/ostler/docs/QA-RUN.md).

**Report.** Every `qa run` ends by rendering `<spec>/qa-report.md` from the ledger — one
section per covered id with its verdict, the step each covering
assertion ran in, observed and expected values, and the screenshots behind it, then every
scenario step by step and a list of warnings (assertions with no
observed value, aborted scenarios). `qa report` re-renders it; `--out-dir LABEL` renders a dry
run's to `qa/LABEL/report.md`; `--ledger` prints the flat listing instead. When the run
recorded its target, each step in the report says where it sits in the video
(`recording 0:14.9–0:16.8`, a link that seeks there) and carries the `qa frames` command
for it.

**Frames.** `qa frames` pulls the frames around a step out of the recording: `--step` takes
the step id the report shows (or a unique fragment of its label), `--at SECONDS` a position
instead (`--target` names which recording when several targets were recorded). One PNG per
`1/--fps` seconds (default 10) of the step widened by `--around` seconds either side
(default 1.0) lands in `<spec>/qa/frames/<step-id>/`, each named by its position in the
recording (`0015.474s.png`), with an `index.md` listing them in order and marking the ones
inside the step's own span. Needs ffmpeg, the same binary the recorder used.

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

## Local environments

`ostler env` renders the services the books' `ops/stack.yml` files declare into one compose file per
copy, and drives docker compose against it. `TARGET` is a book or one `book:service`. With no
target, it is the book you stand in, or every book from the repo root. `--copy` defaults to
`$STABLEMATE_LEASE`, then to `shared`.

An up keeps every service the copy already holds. Naming a book replaces that book's services.
Naming one `book:service` adds or rebuilds that service alone and keeps the rest of its book.

```bash
ostler env check  [--json]
ostler env render [TARGET...] [--copy NAME] [--fixtures SET[,SET]] [--json]
ostler env up     [TARGET...] [--copy NAME] [--fixtures SET[,SET]] [--fresh] [--wait SECONDS] [--json]
ostler env down   [--copy NAME] [--keep-data] [--json]
ostler env ls     [--json]
ostler env schema
ostler env address NAME [--copy NAME] [--json]
ostler env compose [--copy NAME] -- ARGS...
ostler env exec [--copy NAME] -- COMMAND...
```

`exec` runs a command under the secrets the stack root's `secrets:` names. `ls` prints each service with its `about`, its address and the copies that run it, and exits 1 when
the stack files have errors. `schema` prints a JSON Schema for `stack.yml`.

`--fresh` drops the copy's volumes before it comes up, so its fixtures load again. `--fixtures`
replaces each book's `default-fixtures`. `--keep-data` keeps the volumes and the rendered files,
and deletes only the rendered secrets, so a later `down` without it drops the rest.

A bring-up of any copy but `shared` records the process that holds it: the one named by
`$STABLEMATE_LEASE_HOLDER`, which a workflow sets for the commands its run starts. The same
bring-up tears down every other copy on the machine whose holder no longer runs, and names each
one it reclaimed. A copy with no recorded holder stays until someone runs `down`.
