---
name: ostler-book
description: "Write a service's book, the executable Python model of one HTTP or gRPC service that ostler replays against the running app: from its source or from a story, updating it for a commit or a coworker's shipped routes, settling a finding of check, explore or run, a gRPC service and the accounts and refusals services share, a state another service makes (an outside event), and recording what the book cannot see or the app gets wrong. Covers the model of records and states, endpoints, lifecycle matrices, fixtures, journeys and the standing-account world every cell runs in. Web and mobile books come with a later release. Load when writing or repairing anything under a book's services/<name>/ package, when a check, explore or run finding needs fixing, or when backfilling routes a coworker shipped."
applyTo: "**/services/*/model/**/*.py, **/services/*/endpoints/**/*.py, **/services/*/fixtures/**/*.py, **/services/*/journeys/**/*.py, **/services/*/service.py"
tags: [standards, docs]
---

# The service book

A service book is one service written as a model ostler can run. The model says what each
call does to the state, and the runtime plays the same steps on the model and on the live app
and compares the answers. A book imports `ostler.book` and its own modules, nothing else: no
pytest, no other library. The examples in the book are the format. When they and this skill
disagree, this skill is wrong; say so in the pass's report.

The runtime source is not for reading. The one file to open in the installed `ostler/book/`
package is `__init__.py`, which lists every name a book may use; this skill says how each is
meant. A question the skill and the examples do not answer goes in the report under "what the
format could not express".

This release covers HTTP and gRPC books. Web and mobile books come with a later release.

## The package

| Path | Holds |
| --- | --- |
| `service.py` | the `Service` ostler loads: environments, refusal keys, `records`, `outside` events, `unseen`, `diverges`, and `watch`, the list reads the runtime makes after each step to compare rows |
| `model/records.py` | one frozen dataclass per record the service keeps, with its states and the read that tells them apart |
| `model/state.py` | the `State` with one `Collection` per record; a mode of the app is a subclass with its own `rules` |
| `model/rules.py` | one `Rule` per refusal, with the app's message word for word |
| `model/actions.py` | one `Action` per thing a call does: what it accepts, the rules it checks in order, what it reduces to |
| `model/cast.py` | the actors: standing accounts, and the few that need `fresh=` |
| `model/lifecycle.py` | one `Axes` per record: scenes as rows, actions as columns |
| `endpoints/*.py`, `endpoints/shapes.py` | one `Endpoint` per route, every answer it may give, each body shape declared once |
| `fixtures/*.py` | what a caller sends: one base factory per fixture and variants that fill one thing in |
| `journeys/*.py` | stories a user lives through, one class per file |
| `DISAGREEMENTS.md` | numbered entries where the source, the openapi and the app disagree |

Each package has an `ALL` (endpoints, journeys) or `__all__` (fixtures) that registers what
it defines. A class nothing registers does not exist for ostler.

A service that answers gRPC calls, or one of several services in a repo that share accounts
and refusals, is written with [references/grpc.md](references/grpc.md) open: it covers the
`Rpc` declaration, status codes by name, proto field names, the `services/shared/` package
and a world of shared records that a cell cannot make its own copy of.

## Adding a route

Do these in order. Each ends on a check you can run.

1. **Read what the handler reaches.** The controller method, the service it calls, and the
   shared code below it: a stored procedure, a library call, a query. The app's seed data is
   source too: a record no cell made, such as a second category every account sees, comes
   from it. Write down which
   behaviour the book already models; a shared procedure another route already uses is
   modelled once and reused. Done when you can say, for each status the route answers, what
   makes it answer that.
2. **Model the record.** A record the book lacks goes in `model/records.py`, its collection
   on the state, its states told apart by a read a caller can make. Done when the walk
   (`explore --seed-only`) shows no contradiction.
3. **Write the refusals and the action.** One `Rule` per refusal, the action's `rules` in the
   order the app checks them, `reduce` returning what the call does. Details in
   [references/model.md](references/model.md), which covers `State`, `Collection`, `Action`,
   the reduce primitives, `Rule`, `Defect` and the cast.
4. **Declare the endpoint.** Method, path, auth, params, query, body, every answer with its
   shape, `does`, `source` pointing at the handler and the code it reaches, `carries`.
   Shapes go in `endpoints/shapes.py`. Details in
   [references/surface.md](references/surface.md), which covers `Endpoint`, `Answer`,
   `Field`, `Id`, `List`, refusal keys and endpoints an outside event arranges. Done when
   `check` names nothing new.
5. **Place it in a matrix.** A column in the lifecycle matrix of the record it reads or
   writes, and a scene for any state it needs that no scene reaches. An endpoint no matrix
   places is played in every state of the app. Details in
   [references/matrices-and-journeys.md](references/matrices-and-journeys.md).
6. **Give it fixtures and a journey.** A fixture for each state the route needs, registered
   in `__all__`. At least one journey per batch that a user would recognise as a story. A
   later step that names a record an earlier step created takes that step's fixture, or a
   fixture holding it as a field: the id the app answered travels with the object.
   `Fixture.of(record)`, path and query fixtures and `examples` are in
   [references/matrices-and-journeys.md](references/matrices-and-journeys.md#fixtures).
7. **Replay it and settle every finding.** The targeted replay of your endpoints, then the
   targeted run of the same endpoints, which adds the journeys that call them and their input
   classes. Your endpoints are the new ones and every existing endpoint whose action, rule or
   record your change touched: `git diff` over `model/` names them. Fix each `FAIL` as book
   wrong or record it as app wrong. Done when both are at 0 fail.
   [references/findings.md](references/findings.md) says what each finding means and how to
   record what the book cannot see.

The route is done when `check` is at its baseline, the walk has no contradiction, the
targeted replay and the targeted run are at 0 fail, and `index` has refreshed `index.tsv`.

The full `run` plays the whole book, and its time grows with every route. It is the book's
gate, not the batch's: it runs once when a backfill ends and once a night after that. A `FAIL`
there is a batch that left an endpoint out of its targeted run, so the fix names that endpoint
in the next targeted run.

## Backfilling commits

A book follows the app commit by commit. `service.py` names the app's `roots`, the whole source
trees of the service with only tests, mocks, test rigs and seed fixtures ignored, never a
chosen layer: a route lands first in generated code and a contract, a rule in a stored
procedure. The book records the app commit it was verified at.

`ostler book stale services.<name> --app <app root>` is the batch. Each stale
element is an existing endpoint or record to replay. Each changed file or function no element
names is a route or a rule to add, or a `source` pointer to extend down to it; code that holds
no behaviour goes in the app's `ignore` as `path` or `path::function`. Each decision listed is
one to reread. Work them through "Adding a route", then `verified` records the app's HEAD. Done
when `stale` lists nothing.

When the commit answers a story, the story is the intent: read its model, plan and review
answers before the diff, and write the delta from them. The latest decision wins. A review
answer or the commit message that changes what the model said is the intent now, and the
older line is recorded as settled, never as an app defect.

A check that shows the app breaking the intent stays in the book. A red journey is the right
result until the defect is declared known; a journey or probe removed to get green leaves the
defect where no run will notice it being fixed or growing.

## The world every cell runs in

The app is never wiped. Every cell, every journey and every coworker shares the same
standing accounts, so the app holds records the book never made. Write as if the app were
already busy:

- **A cell makes what it acts on.** A scene's steps create the records the column aims at.
  Ids come from the app's answers; a fixture learns its id from the `creates=` answer. Never
  write an id the app issues.
- **A list is read as containing.** The runtime compares a list only on the entries the
  book made. Never assume a list is empty, and never assert a count of everything listed.
- **An outcome that counts the account's whole history needs `fresh=`.** A quota, a usage
  total, a "first time" banner. Declare the actor with `fresh="<why>"` and it gets a new
  account per cell, so the count starts at zero and the book asserts it. A field made opaque
  because a standing account's history swamps it is a `fresh=` actor missing.
- **A write that changes the account itself belongs to a `fresh=` actor.** A purchase, an
  authorization, a setting: a cell that makes one on a standing account leaves it for every
  later cell, and nothing takes it back. Such a fixture's `examples` yields nothing for a
  standing actor, so the walk never plays it on one. Every other actor is a standing account.
- **An account the app must not list**, such as a fresh member that would show in a list of
  recipients under a name the book cannot know, is a cast member with no user record.
- **A value the caller types and the book never issued** is `Id(kind, strangers="<why>")`:
  the runtime reads it back as written instead of as an unknown id.
- **An order the app does not fix** is `List(shape, unordered="<why>")`, the why naming the
  tie the app leaves open.
- **Nothing tears down.** The backstage arranges; it has no wipe, sweep or delete. A record
  only the outside world makes (a mail arriving, a stock feed) is arranged by an outside
  endpoint, never by writing to the store.
- **A backstage write sets the row the app made.** When the app creates a companion row for
  every new record (an empty container, a settings row), the backstage updates that row and
  never inserts a second one beside it. A twin row makes the app answer what no user ever
  sees, and a model fitted to that answer passes while describing a fiction.

## The environment is judged first

A run on a sick environment says nothing about the product, so the runtime refuses to judge
one. `Service.health` lists journeys, defined in `services/<name>/health.py`, that read the
standing world every other journey relies on (the reference data the fixtures load, the
standing accounts' records) and make one round trip through the core of the product. They
run before anything else. The run stops with exit 3 and `could not judge: <why>` when a host
does not answer, a gateway answers 502, 503 or 504 the book does not declare, or a health
journey fails. Nothing played before the stop is a verdict: fix the environment and rerun,
never the book. A health journey is a journey like any other, judged against the model, so
it changes when the standing world changes.

## The commands

Run from the directory that holds `services/`, one at a time. Never start a second `run` or `explore` while
one is live.

| Command | Takes | Tells you |
| --- | --- | --- |
| `ostler book check services.<name>` | seconds, no app | the format: unregistered endpoints, journeys or rules, unplaced endpoints, modules nothing imports, missing source pointers |
| `ostler book explore services.<name> --seed-only` | seconds to minutes as matrices grow, no app | the model's walk to depth 4; run it after every change to a fixture, a scene or an endpoint; "the book contradicts itself" means a fixture arranges a record that cannot exist |
| `ostler book explore services.<name> --no-stack --only <A>,<B>` | about 2 s a cell | every cell of the named endpoints on every state the walk reaches, against the app |
| `ostler book run services.<name> --no-stack --only <A>,<B>` | a few minutes | the journeys that call the named endpoints, their declared cells and their input classes, including divergences declared for them and never met |
| `ostler book run services.<name> --no-stack` | tens of minutes | every journey, every declared cell and every input class; the book's gate, run when a backfill ends and nightly, never per batch |
| `ostler book index services.<name>` | seconds | rewrites `index.tsv`, which `search` reads |
| `ostler book stale services.<name> --app <root>` | seconds, no app | the elements whose source changed since the verified commit, changed files no element names, decisions they touch |
| `ostler book verified services.<name> --app <root>` | seconds | records the app's HEAD once `stale` is worked |

`--only` takes endpoint class names, never journey names. `explore` and `run` print nothing until they end, and a long one may outlive the shell's
wait. Send the output to a file and read its last lines once the command has exited.

`search <term>` and `explain <Endpoint|Journey|Action>` answer what the book already says
before you read any source. While authoring, `explore` against the app always takes `--only`: the full replay is the
gate's job. The seed-only walk needs no app and runs as often as you like.
