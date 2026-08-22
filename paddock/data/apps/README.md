# `data/apps/` — the benchmark fixtures

One directory per app, and the directory name *is* the name a task module points at. Two
kinds of fixture live here, and they are never interchangeable — one is a starting line,
the other a finished race with an answer key:

- a **backlog** is input to *building* an app: `docs/backlog.md`, the `docs/decisions/`
  records standing behind the product decisions it leaves open, and the `grill/` capture of
  the one operator turn the author lane reserves for a human. `apps/link-shortener/` is
  what a task named `link-shortener` runs on.
- a **frozen app** is input to *measuring QA*: finished code, a book, stories, and defects.

They shared a namespace deliberately. Which kind a fixture is is a property of the *task*
that names it — greenfield rounds read the backlog, QA rounds read the answer key — and
nothing in the harness ever switched on which directory it came out of, so the two-tree
split encoded a distinction that only ever lived one level up. Every path here is an
explicit string in a task module either way.

The rest of this file is in two halves: the backlogs first, since they are the shorter
story, then the frozen apps and the rules their answer keys rest on.

## The backlogs

They are not the same size, and that is the point. `todo-app` answers *how good are these
workflows* — four surfaces, eighteen bullets, hours per run, one sample. That is the right
instrument for a verdict and the wrong one for a fix cycle: a defect in the coder's fifth
node costs most of a day to reach twice, so you get one or two observations a day and every
one of them is confounded by the dozen things that happened before it.

The other three answer *did the workflows get stuck, and where* — which is a question you
need answered repeatedly, cheaply, and today. Their scores are deliberately not comparable
to `todo-app`'s, or to each other's: a smaller backlog is an easier backlog, and the number
they produce is only meaningful against the same backlog's own history.

| Backlog | Surfaces | Bullets | Budget | Task | What it is for |
|---|---|---|---|---|---|
| [`link-shortener`](link-shortener/docs/backlog.md) | api (Go) | 3 | 30 min | `link-shortener` | The smoke run. Fast enough to re-run after every fix, small enough that a failure has one cause. |
| [`expense-split`](expense-split/docs/backlog.md) | api (Go) | 5 | 60 min | `expense-split` | The workload run. Enough stories for the coder to loop over, which is where staleness and churn actually appear. |
| [`bookmarks`](bookmarks/docs/backlog.md) | api (Go) + web (React Router) | 4 | 60 min | *not yet written* | The cross-surface run. Two surfaces is where story decomposition, plan-context and per-stack templating go wrong; one surface never exercises any of it. |
| [`todo-app`](todo-app/docs/backlog.md) | api + web + app + infra | 18 | none | *not yet written* | The verdict run. The only score that means "how good are these workflows", and the only task that costs hours per cell. |

```bash
uv run paddock run link-shortener --label smoke
```

A backlog with no task module beside it is a fixture nothing can run yet — the input is
written, the declaration (surfaces, scaffolds, repo gates, judge) is not. That is a real
gap and is left visible rather than papered over.

### What makes the hour-sized ones finish in an hour

Two things, both deliberately data rather than machine state. `todo-app` sets neither on
purpose: the verdict is only meaningful at the tier you actually ship on, and a ceiling on
a run that long stops it mid-backlog and scores a repo nobody finished.

**The pinned config.** Which model a node runs on is the largest single term in both the
score and the wall-clock, so leaving it to whatever `~/.config/stablemate/config.toml`
happens to say makes "finishes in an hour" a property of the laptop. A task names a full
config under [`../configs/`](../configs/) instead, and that file carries the `[power.*]` /
`[profiles.*]` tables — which is why the harness has no model vocabulary of its own, and
why swapping models is swapping one file rather than threading a flag.

It is a *whole* config rather than an overlay because `load_config` does not merge: an
explicit config means *this file and no other*, so the tracked one must also carry the
machine truth a partial file would drop (`library_dir`, `stablemate_dir`, the `[harness.*]`
tables).

**The per-phase budget.** `Fixture.budget_s` names a wall-clock ceiling per phase,
enforced by workhorse's own `WORKHORSE_MAX_RUNTIME_S` and overridable for one round with
`--param budget_<phase>=N`. That matters more than it looks: the ceiling is checked
*between* states, so an over-budget run stops at a node boundary with its checkpoint and
its artifacts intact — scoreable, and resumable. A `timeout(1)` around the process would
instead kill it mid-node and destroy the evidence you started the run to collect.

A budget is a *diagnostic*, not a target. A run that hits its ceiling has told you
something; read the reliability half of its scorecard before you raise it.

### The packs are derived, not chosen

Every task installs the same repo-level packs — `product-planning`, `stablemate`,
`infra` — plus its surfaces' stack packs, and `ui` alongside `react-router`/`flutter`.
That list is not taste. It is what you get by walking the author's and coder's prompts
for every `instruction_ref` / `skill_load_ref` / `find_by_tags(...)` call site and asking
which pack supplies an answer.

The reason to derive it rather than pick it: a benchmark installing fewer packs than a
real repo of the same shape is not an easier version of the benchmark, it is a
*different* one. The workflows then run against fallback prose — "(none installed —
follow `AGENTS.md`)" — and the score measures how well an agent copes with a repo nobody
ships, while the run you actually care about had the skills all along.

Two failure modes, and they are not the same size:

- **`find_by_tags` renders a fallback.** Degraded, not broken — the prompt says what to
  do instead. Before this list was derived, `find_by_tags('runbook')` matched *nothing in
  the whole library*, so all four of its call sites (`triage-qa`, `apply-review`,
  `apply-qa-fixes`, `qa-fix-item`) took the fallback on every run. `infra` is the only
  pack that answers it.
- **`skill_load_ref` names a skill that is not there.** Not degraded — the coder's
  `document_story` and `code_review` prompts do not ask what the repo has, they say "load
  this and follow it" and name `ostler-documentation` and `code-review`. Absent, the
  agent is handed a slash command or a path that does not resolve. Both skills are in the
  `stablemate` pack, which is also the only pack the benchmark uses that ships in
  `base-library/` rather than the private overlay — so a public clone resolves it.

`architecture` and `testing` are not listed anywhere and do not need to be: `go`,
`react-router`, `flutter` and `pulumi` all `includes:` them. The prompts-only packs
(`qa`, `shared-lifecycle`, `shared-docs`) are deliberately left out — a Python workflow
renders its own package-local prompts and never reads the library's, so installing them
would add commands nothing invokes. `shared-docs`'s *scaffold* is a separate thing and is
already named explicitly by `docs_scaffold:`.

Changing this list changes what the round installs, and therefore what its score means: a
number from before the packs resolved is not comparable to one from after. Say so beside
any comparison that spans the change.

### Why three small ones, and not one

Each isolates a class of failure the others cannot reach.

One surface with three bullets produces one epic and a handful of stories: if that run
churns, the cause is in the single-story path, with nothing else in the frame. Five
bullets produce enough stories for the coder to *loop*, which is the only way to see the
selector re-pick, a repair loop repeat, or a run go stale mid-queue — a three-bullet run
finishes before any of those has a chance to show. Two surfaces produce stories that
span stacks, which is where the plan-context layer maps, the per-stack skill resolution
and the prompt templating all get exercised for the first time; a Go-only run resolves
one pack and proves nothing about the second.

Backlogs are written to the same contract as `todo-app`'s: user-observable behavior,
`- [kebab-id] A person …`, no implementation tasks. A bullet that names an
implementation is a bullet the author workflow cannot be judged on, because it has
already been decomposed for it.

## The frozen apps

A frozen app ships four things:

| Part | What it is |
| --- | --- |
| the code | a runnable service, small enough to read in one sitting, with a `compose.yml` |
| the book | an OKF subgraph under `docs/features/`, every normative bullet carrying a `verify:` check call |
| the stories | an epic, its stories, and a spec dir per story under `docs/specs/` |
| the answer key | `defects.yml` plus whole-file variants under `defects/`, each naming the obligation it should contradict |

Nothing in an app is generated by an agent. It is hand-written precisely so that what QA is scored
against is a **documented** expectation rather than a previous run's output — a fixture harvested
from a passing run cannot tell you whether QA catches anything, only whether it agrees with itself.

## Why the tree carries no `.git`

QA mints its obligations from *uncommitted* changes: the coder QA lane builds its OKF context with
`base="HEAD"`, `head="WORKTREE"`. A plain checkout of a finished tree therefore obligates nothing at
all — every file is committed, the diff is empty, and the run has nothing to prove.

So a trial materializes the git state instead of inheriting it. Each story carries images of the
files it touches:

```
stories/<story>/pre/<path>     the file as it was before this story
stories/<story>/post/<path>    the file as it was after this story, when that is not the app tree
stories/<story>/diff.yml       changed: […]   added: […]
```

Materializing story *S* means: copy the app tree, `git init`, commit a *before* tree (each `changed:`
path replaced by its `pre/` copy, each `added:` path deleted), then restore S's own files into the
worktree uncommitted — from `post/<path>` where that exists, from the app tree otherwise.
`HEAD..WORKTREE` is then exactly S's implementation diff, which is the situation a QA run is
supposed to face — provided the book in that image is the book S was written against, which is the
subject of the next section.

`post/` is what keeps the *first* story's diff from containing the last story's code. The app tree is
only the post-image of the final story; every earlier one that keeps extending the same module needs
its own snapshot, or a trial on story 1 would present three stories' work as story 1's and QA would
be scored on obligations nobody claimed to have implemented. A story with nothing to pin carries no
`post/` directory at all, and the last story never has one.

The trial directory must be named after the app (`seat-booking`, not `trial-1`): farrier derives every
generated skill name from the repository directory's basename, and the spec dirs name those skills.

### The book is versioned per story too

A book authored in one pass against the finished app is **wrong for every image but the last**. It
documents commands, fields and invocations that story 1 has not written yet, and a plan authored
against it reaches for them: a QA plan for `tally-cli`'s first story that calls `tally report --json`
crashes on a trial, because `report` arrives two stories later. The book is not a fixed backdrop the
stories move against — it is one of the files the stories change, and it materializes like any other.

So a story lists the book pages it is described on in its `diff.yml` `changed:` list, and ships
**the same trimmed bytes in both `pre/` and `post/`** — the book as of that story, describing what
exists by the end of it and nothing later. Identical halves are the point, not an oversight: `pre/`
puts that image in the *before* commit and `post/` puts it in the worktree, so the book is present
and current in the trial while contributing no line to `HEAD..WORKTREE`. A book that differed
across the two would be a changed path in the story's own diff, and would then need a `code:` owner
of its own to avoid an `unmapped-change` error. Omitting `post/` is worse than wrong-looking: the
materializer falls back to the app tree, which restores the *finished* book and puts the
anachronism straight back. The last story is the one exception, for the same reason it needs no
`post/` at all: the app tree already holds its image of the book.

Two corollaries worth having in front of you before you author the next fixture:

- **`depot-infra` and `policy-desk` escape this only because they ground at file level.** A
  file-level citation is satisfied by the file existing, so an anachronistic bullet above it costs
  nothing and nothing goes red. That is a latent gap in those fixtures, not a property to imitate —
  the moment their grounding goes symbol-level, the same crash arrives.
- **`okf-builder` builds books from finished code**, so any fixture derived through it inherits the
  anachronism by construction. A generated book is a post-image of the *last* story and has to be
  trimmed backwards, per story, by hand.


Only `stories/`, `defects/` and `defects.yml` are held back from that copy. **Everything else at an
app's root is handed to the agent under measurement**, which is why no app carries a `README.md` of
its own: a fixture's own notes are about its answer key, and a file explaining which lines were
sabotaged would be sitting in the worktree QA is being scored on. Each app's notes live in
[The apps](#the-apps) below instead — outside every tree a trial materializes.

## The answer key's one non-obvious rule: an obligation is only scorable if the story owes it

Every row of `defects.yml` names the obligation the seeded file makes false. That id has to be
one the story's trial is **required** to evidence, not merely one the book mints: the evidence
map is built over `[o for o in scope if o.get("required", True)]` and nothing else, so a row
pointed at a context-only obligation returns `inconclusive` — *"obligation not owed by this
trial"* — forever. It can never be a catch and never a miss.

Owedness is not a property of the book alone, and it is decided by two rules pulling opposite
ways. A `code:` citation stops localizing the change once enough nodes share it — for a bare
file with no symbol behind it that is the second node, because a bare-file citation shared by
several nodes localizes nothing; for an exact symbol it takes `_CONTAINER_FANOUT` (three),
since two nodes citing one function is a book written well rather than a container. Pulling
the other way, a node is *also* owed when it names the same relation `subject:` — the record,
the event, the lock — as a node the change reached directly, stamped `relation-of-required`.
That is the split-story case: the screen that creates the record the story reshaped is out of
scope and broken by it all the same. A node reached only that way owes live evidence for the
relation bullets themselves and for its `contract`, and keeps the rest of its surface as
context — the hop asks whether the shared invariant survived, not whether an untouched node's
whole documented behaviour did. A fixture author gets both rules by naming subjects on
relation bullets and by following a layout rule stronger than "one file per concern":

> **One OKF node per source file.** A component extracted into its own file is scorable; two
> components sharing a file are context, and every defect seeded in either is unscorable.

`policy-desk` is laid out to that rule — its two HTTP handlers live in `update.go` and
`cancel.go` rather than one `amend.go`, and `FieldError.tsx` and `RegisterError.tsx` are their
own files — and `tests/test_policy_desk_app.py` pins it by minting each story's packet the way
QA mints it and asserting every row's obligation comes back owed. It is pinned by a test
because the way it breaks is an ordinary refactor that touches neither the book nor the key.

## Every file a story touches needs a `code:` bullet — including one a typed bullet already names

QA's obligation packet maps a changed path to the node that owns it through `code:` bullets and
nothing else. A path no `code:` bullet claims is an `unmapped-change` **error** in the packet, which
is a block against the trial rather than a signal about the app — so a fixture's book has to own
every file its stories add or change, including the ones that are nobody's source code: a compose
file, an emulator config, a seed script, a stack config. The `environment` node is where those
belong (`claims-api`'s does), and its `code:` key exists for exactly this.

The case that surprises: a contract file named by a **typed** bullet is still unowned. `- openapi:
app/api/openapi.yml` says what the document *is*; it does not map the path, because the mapper reads
`code:` alone. So the convention across all three fixtures is a redundant `code:` bullet beside the
typed one — the same path listed twice on the same node, once for the reader and once for the mapper.
It reads like a mistake and is not; teaching the mapper to route through `openapi:` would change what
`unmapped-change` means, which is a Part II decision rather than something a fixture author gets to
make.

## Ports belong to the spec

**The benchmark owns `18080-18099` and nothing else**, and every fixture here draws from
that one register, because a fixture that measures QA and a round that builds an app can
easily be running at the same moment on one machine. A surface that listens names its port
in its backlog's surface list, and no two fixtures share one: `expense-split` api 18080,
`link-shortener` api 18081, `bookmarks` api 18082 and web 18092, `seat-booking` 18083,
`policy-desk` 18084, and `claims-api` 18085 with its auth emulator on 18086. A new fixture
takes the next free number in the range and writes it down the same way.

A fixture that stands up a *dependency* registers that port too. `claims-api` runs a Firebase
Auth emulator beside the service so identity is minted without a credential, and the emulator
listens on a port of its own — unregistered, it would take the tool's default `9099` and
collide with any other project's emulator on the same machine.

**`depot-infra` and `tally-cli` claim no port at all, and that is worth writing down.** The first
is a Pulumi program: nothing serves, nothing is deployed, there is no `compose.yml` and no stack
to bring up — its whole observable behaviour is the plan `pulumi preview` writes to a file. The
second is a command: it runs, writes a JSON file and exits, and a QA scenario reaches it over a
process boundary rather than a socket. A fixture with no entry here is otherwise indistinguishable
from one whose author forgot, so both absences are registered rather than left blank.

This is not tidiness. A backlog that starts a server without naming a port gets the language's
idiomatic default — `8080` for Go, `3000` for React Router — and those are the two most
contended ports on a developer machine. An `expense-split` run bound its QA daemon to `8080`
while an unrelated project's stack already held it, so the readiness probe
(`POST http://localhost:8080/groups`) was answered by a stranger's service. The daemon lost
the bind and the run failed loudly, which is the *good* outcome and the one we did not
choose: had our app come up first, QA would have graded a foreign API and reported a verdict
about it, with nothing in the evidence to say so. Naming the port removes the coin flip.

The backlog is the right home for it even though it is otherwise strictly
behavior-not-implementation, because the port is neither — it is a fact about the machine
the app is allowed to occupy, and the backlog is the one document every phase reads.

## The frozen apps, one by one

- **[`seat-booking/`](seat-booking/)** — one showing, twelve seats, three transitions
  (hold / release / confirm) over a JSON ledger, plus a server-rendered seat map. Port **18083**.
  Chosen because its natural failure modes are the check vocabulary itself: a compare-and-swap
  refusal, a count over a map, a neighbour left unperturbed, a booking that survives a restart.

  That last one needed a seam the fixture did not have. D1 and D2 sit on `confirm-booking`,
  whose AC5 is durability across a service restart, and until this app's `agents.yml` opted
  into the `docker` QA tool there was no sanctioned way for a plan to restart anything: the
  planner blocked rather than pass an immediate read-after-write off as proof, and the trial
  parked at the operator gate instead of reaching a verdict. **D1/D2 detection numbers only
  exist from that opt-in onward** — a round predating it scored no `confirm-booking` trial at
  all, so a scorecard from before it is not a baseline for one from after.

  The same round found the other half of that debt: each transition now lives in a module of
  its own — `app/hold.py`, `app/confirm.py` — rather than sharing `app/booking.py`. The frozen
  book is not story-scoped, so every trial checks out all of it and every cited symbol has to
  exist in every story's worktree; while the three transitions shared one file, story 1's and
  story 2's `post/` images of that file trimmed the symbols the book cites for the others, and
  `ostler doctor` failed `missing-code-symbol` before a single scenario ran. **No `seat-map` or
  `seat-hold` trial could reach a verdict either**, for the same reason and over the same span
  as the restart gap — this app produced no scoreable round before both were fixed.

- **[`policy-desk/`](policy-desk/)** — an insurance policy register: a Go JSON API behind a React
  single-page client, three stories (create, list, amend) over the same ledger. Port **18084**.
  Chosen for the interest cases one Python module cannot pose — a deep link that has to survive a
  page load, a route change the client owns rather than the server, a conditional field rule that
  only exists for one coverage type, and an optimistic-concurrency token carried through a form.

  Its eleven-row key is built around those cases rather than around detection alone. **P1 is
  expected to be missed by today's QA**: the register's "New policy" link renders with the right
  role and the right name and does not navigate, while the form stays reachable by its address,
  so a plan that opens screens by URL proves the whole form and never touches the broken thing.
  Nothing gates that — the `entry` bullet is consumed by no check — and a missed P1 printed
  beside a non-zero `deep-links` count is the fixture working. **P9–P11** are catchable only
  through the auditor's reading of the evidence: a refusal in the wrong shape carrying the right
  sentence, a route change that throws into the console while the screen recovers, and a failed
  re-read swallowed behind rows that still look current. No declared check fails in any of them.

- **[`claims-api/`](claims-api/)** — an insurance claims desk: a Go JSON API generated from an
  OpenAPI contract, with bearer identity minted by a Firebase Auth emulator running beside it.
  Three stories (submit/list, tenancy, adjudication) over one JSON ledger. Port **18085**, and
  **18086** for the emulator. It mirrors a production OpenAPI→Go (oapi-codegen v2 + chi) service,
  and it is the first fixture with **no GUI at all** — its book is `http/` and nothing else, which
  is the shape the trio exists to measure: what the leverage keys read when there is no screen to
  deep-link into.

  Its nine-row key sits on the two things a contract-first service can get wrong that a hand-rolled
  one cannot pose. Authorization is **not** hand-wired per route: `oapi-codegen`'s chi wrapper
  stamps `BearerAuthScopes` into the request context for exactly the operations `openapi.yml`
  secures, and the middleware skips anything it does not find there — so the contract document is
  load-bearing for protection, and C1/C2 make it false in ways that leave every happy path green.
  C9 is the only row catchable by the auditor alone: a refusal whose `detail` quotes the token it
  rejected, which no declared check can see because the status code is right.

  **Toolchain.** The module floor is `go 1.25.0`, which is not a taste — `firebase.google.com/go/v4`
  pulls `cloud.google.com/go/firestore` and `golang.org/x/oauth2`, and both require it. A host on
  an older Go builds it anyway through `GOTOOLCHAIN=auto`; the Docker build pins `golang:1.25-alpine`
  so it does not depend on that. The generator is pinned at its call site — `go run
  github.com/oapi-codegen/oapi-codegen/v2/cmd/oapi-codegen@v2.5.1` in `app/api/Makefile`, no
  `tools.go` — and `gen/` is committed, because a fixture that regenerates its own code at trial
  time is measuring the generator's availability rather than QA.

  **Provenance (deviation, recorded deliberately).** This fixture and its two siblings were
  hand-authored end to end — book included — rather than run through genesis → author →
  okf-builder → hardening. That was a design ruling on 2026-08-21: these fixtures measure the QA
  lane over a *frozen* book, okf-builder has never produced an http-only book, and Part II's
  spec-mined pre-pass is what changes that. The consequence to hold on to: **nothing about these
  three fixtures is evidence about the authoring lane.** A claim that okf-builder produces books
  of this shape has to come from running it, not from reading these.

- **[`depot-infra/`](depot-infra/)** — an artifact depot declared as infrastructure: a Pulumi
  program in Go that creates a versioned GCS bucket, a readers binding, a deploy service account
  with one bucket-level grant, a Secret Manager secret and a nightly Cloud Scheduler sweep. Two
  stories (`artifact-store`, `deploy-identity`). **No port, and no stack**: nothing in this app
  serves, nothing is deployed, and there is no `compose.yml` to bring up.

  That absence is the measurement. `claims-api` removed the screen; this one removes the process.
  The app's entire observable behaviour is the plan `pulumi preview` writes, so the QA lane's only
  evidence is a JSON document — read with `jq`, taken by the `make -C pulumi plan` target the app's
  own ops page publishes (`agents.yml` opts QA into `make` and `jq`, and nothing else).

  Its seven-row key is built around the way a *declaration* goes wrong. A widened IAM binding, a
  project-level grant beside the narrow one, a second scheduler job and a token in the clear all
  produce a plan that previews cleanly and reports no error at all — the resource the story is
  proud of is still there, still correct, and every assertion that reads it by name still passes.
  Only an assertion written over the whole plan separates them: the member list compared *as a
  list*, every IAM step enumerated, the jobs counted. Whether the lane writes that kind of
  assertion is the whole question D1–D6 ask.

  **D7 is the row this evidence surface cannot see.** Deleting the program's `pulumi.Version` pin
  changes no step in the plan on any machine that already holds a plugin — the preview reports the
  version it resolved, not the version the program asked for — so it is filed `caught_by: audit`
  and its trial's obligation comes back `covered`. It is in the key because the miss is the point.

  **Where the claims live.** Every normative claim here is a `consistency:` bullet on a concept
  node, not a `### field` section: `consistency` is normative on every node type, and the field
  sections that were written first parsed clean and minted **zero** obligations. See
  `defects.yml`'s header for the full note and the flex finding it cites.

  **Toolchain.** `pulumi v3.191.0` with the `gcp` provider plugin at **8.16.0**, which the program
  pins at the provider (`pulumi.Version(providerVersion)` in `pulumi/main.go`) rather than taking
  whatever the host has installed. `go.mod` declares `go 1.25.11`; a host on an older Go builds it
  through `GOTOOLCHAIN=auto`. `vendor/` is **never** committed — `go.sum` is the integrity story.
  Two warmup commands prime a cold machine, and neither is part of a trial:

  ```bash
  (cd pulumi && go mod download)              # module cache + the go1.25 toolchain
  pulumi plugin install resource gcp 8.16.0   # the provider the program pins
  ```

  **Offline.** No credential is needed and no Google API is reached: a preview resolves against the
  plugin, not the cloud. Verified rather than assumed — with the module proxy off (`GOPROXY=off`)
  and every `*_proxy` variable pointed at a closed port, `make -C pulumi build` and `make -C pulumi
  plan` both exit `0` and produce the **identical 9-step plan** (`changeSummary {"create": 9}`) as a
  run with the network up. The provider's `failed to get regions list` warning is present in both
  runs and is not an error in either. The stack's local backend is a directory beside the program
  and its passphrase is a fixed string, both stated in `pulumi/Makefile`: there is no `pulumi
  login` anywhere in this fixture, in a step or in a test.

  **Provenance (deviation, recorded deliberately).** Hand-authored end to end, on the same 2026-08-21
  ruling as `claims-api` above — see that entry for what it means. Nothing about this fixture is
  evidence about the authoring lane.

- **[`tally-cli/`](tally-cli/)** — a shared-expense ledger as a stdlib-only Python command:
  `init`, `add`, `import`, `report` and `export` over one JSON file, plus a global `--file`.
  Three stories (`ledger-init-add`, `import-csv`, `report-export`). **No port and no stack**, for
  a different reason than `depot-infra`'s: this one runs, but it does not listen.

  Its subject is **granularity**. All three stories edit `tally/cli.py` and two of them
  `tally/ledger.py`, so file-level ownership separates nothing at all — every defect is seeded in
  a module some other story also touched. What decides whether a row is scorable is symbol-level
  grounding: each `code:` bullet names a function, and a single citation demoted to a bare file
  takes every obligation behind it out of scoring and returns `inconclusive` forever, which reads
  exactly like a QA lane that never answered. `test_tally_cli_app.py` mints each story's packet
  the way QA mints it and asserts every row's obligation comes back owed.

  All seven rows are `caught_by: run`. `claims-api`'s C9 and `depot-infra`'s D7 already cover the
  audit-only arm of the scorer, and a third would buy nothing over them.

  **The QA lane here has no service in it.** A plan may not import the package — `ostler.qa.lint`
  is an AST allowlist — so a scenario reaches the product the way it would reach a compiled
  binary: `python3 -m tally`, through the `python3` tool `agents.yml` opts into and the
  `[qa_tools.python3]` table in `configs/opencode.toml` resolves. The QA target's `driver` stays
  `python`: that names the harness a scenario body runs in, not the transport, and there is no
  driver for "a command".

  **The book is versioned per story**, which is the rule [above](#the-book-is-versioned-per-story-too)
  and which this fixture is where it was found. Symbol grounding is what exposes it: a bullet
  naming `tally/report.py::summarize` is a dangling citation in the two images that have no
  `report.py`, and a plan authored against the finished book calls a subcommand two stories early.

  **Provenance (deviation, recorded deliberately).** Hand-authored end to end, on the same
  2026-08-21 ruling as its two siblings — see `claims-api`'s entry for what it means. Nothing
  about this fixture is evidence about the authoring lane.
