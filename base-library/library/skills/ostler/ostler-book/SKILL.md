---
name: ostler-book
description: "Write a service's book, the executable Python model of one HTTP or gRPC service that ostler replays against the running app: from its source or from a story, updating it for a commit or a coworker's shipped routes, settling a finding of check, explore or run, a gRPC service and the accounts and refusals services share, a service that calls another service and the records that service owns, a state another service makes (an outside event), which inputs and twins a run tries on a field, and recording what the book cannot see or the app gets wrong. Covers the model of records and states, endpoints, lifecycle matrices, fixtures, journeys and the standing-account world every cell runs in. A web or mobile app is a screen book, written with screens and interactions in place of endpoints. Load when writing or repairing anything under a book's services/<name>/ package, when a check, explore or run finding needs fixing, or when backfilling routes a coworker shipped."
applyTo: "**/services/*/model/**/*.py, **/services/*/endpoints/**/*.py, **/services/*/fixtures/**/*.py, **/services/*/journeys/**/*.py, **/services/*/service.py, **/services/*/*/service.py, **/services/*/screens/**/*.py, **/services/*/interactions.py, **/services/*/surface.py, **/services/*/*/model/**/*.py, **/services/*/*/endpoints/**/*.py, **/services/*/*/fixtures/**/*.py, **/services/*/*/journeys/**/*.py, **/services/*/*/*/service.py, **/services/*/*/screens/**/*.py, **/services/*/*/interactions.py, **/services/*/*/surface.py"
tags: [standards, docs]
---

# The service book

A service book is one service written as a model ostler can run. The model says what each
call does to the state, and the runtime plays the same steps on the model and on the live app
and compares the answers. A book imports `ostler.book` and its own modules, nothing else: no
pytest, no other library. The examples in the book are the format. When they and this skill
disagree, this skill is wrong; say so in the pass's report.

The runtime source is not for reading. A signature, a member or a method's effect comes from
`python -m pydoc ostler.book.<Name>`, for any name `ostler.book` exports: `Browser`, `State`,
`Collection`, `Become`, `Signed`, `Service`, `PageSurface`. It prints the signature and what each
method does, from the repo's venv and from a client repo alike. This skill says how each name is
meant. A question the skill, pydoc and the examples do not answer goes in the report under "what
the format could not express".

This release covers HTTP, gRPC, web, mobile and command-line books.

## The bar

A book is held to four properties at once. Fall back on them when no rule below covers the
case in front of you.

- **True.** Every claim is one the running app is asked to show. A claim no call and no
  screen can observe stays out of the book.
- **Complete.** Everything the service does is in the book. Every endpoint, screen and
  command sits on a journey or a cell the runtime plays.
- **Sufficient.** A reader holding only the book can bring the stack up, reach any screen
  and make any call.
- **Intelligible.** The book says why a behaviour is so. Each decision is a file under
  `decisions/` that names the elements it explains. The Python holds what runs and a decision
  holds only the why, so a decision links to the element by name and never restates a shape or
  a status the Python declares.
- **About the product.** A book covers what the product does. Concurrency and restart belong to
  the app's own tests, and a driver waits on an event the app emits, never on a timer.

## The package

In the artifacts folder a service's book is `services/<repo>/<name>/`, and its module is `services.<repo>.<name>`. `<repo>` is the repository's name: the workspace member name, else the repository folder's name in lower case with `.` and `_` written as `-`. A surface-split book sits one level deeper. Below, `services.<name>` stands for the book's module, which is `services.<repo>.<name>` in the artifacts folder. A repository that publishes its own book sets `book: {home: repo}` in its `agents.yml` and keeps `services/` and `product/` at its root. A repository with no key that still holds an ostler book is refused, and the message names both ways out: set the key, or move the book following `docs/guide/moving-a-book-to-the-artifacts-folder.md`. Two repositories in one artifacts folder can each keep a book of the same name. A book of another repository is named by its full module, as in `owner="services.<other>.<name>"`. A repository with `book.home: repo` keeps `services/<name>/` and the module `services.<name>`. `ostler book search` with no `--service` reads the books of the repository it is started in, and every repository's when started in the artifacts folder. A flat book left at `services/<name>/` in the artifacts folder is named with `ostler book move` by `search` and by the "no book" error. That command moves it into its repository folder and rewrites the dotted module names. A bare `source` pointer resolves against `--app`, the code checkout. A pointer into another repository is `repo://<member>/<path>::<symbol>`, and a lone repository is named by its repository name. A stack or a process that starts the app from a member repository takes the member's folder from `checkout("<member>")`. A run launched with `--worktree` from a workspace works on its own branch. Its book root is the artifacts worktree on that branch and a member's folder is its worktree on that branch, and `ostler` reads both from git when run inside one of them.

A book change is committed in the artifacts repository on a branch with the same name as the code branch of the same work, and for a story that is the story's branch. `ostler book branch` opens it as a worktree and prints the book root. It lands when the code lands, with `ostler book land`, by rebase and fast-forward. A change committed straight on the code's base commits its book straight on the artifacts base. With `book.home: repo` the book rides the code's branch and commit.

The layout:

```
ai-artifacts/
  services/<repo>/<name>/        service book: what one service does
    decisions/                   why, tied to an element of that service
  services/<repo>/ops/           the repository's stack root
  products/<product>/            product book: one markdown page per rule
  teams/<team>/                  team book
  company/                       company book
  epics/  specs/  backlogs/      as before

<repository with book.home: repo>/
  services/<name>/   product/    a tool that publishes its own book
```


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
| `decisions/<slug>.md` | why one behaviour is so: three header lines, `story:`, `date:` and `elements:` with the class names it explains, a blank line, then prose. A decision no story settled, as in a backfill, writes `story: none`. The header may add `sources:`, a comma separated list of what the project wrote down, each one a commit sha, `<sha>:<path>` for a file as that commit held it, or an element's source pointer (`path`, `path::symbol`, `repo://<member>/<path>`), and `check --app` opens each |
| `<artifacts dir>/products/<product>/<slug>.md`, or `product/<slug>.md` beside `services/` with `book.home: repo` | a rule above one service, beside `services/` and not inside a book: the product's words, a constraint no story may break, where the truth for a calculation lives. Header lines `date:` (required), `sources:` and `status:` (optional, who said it or where it is written, and a free text such as `accepted` or `superseded by <slug>`), a blank line, then prose whose first line is the page's statement. It names no story and no element. `ostler book search` reads it with every query and `--kind product` shows only it. A why that explains one element stays a decision |
| `QUESTIONS.md` | one line per why nothing written settles, `- <Element>: <question>`; an answered question becomes a decision and its line is removed |
| `FORMAT` | the commit of this skill's source the book was last judged against, one sha. The workflow writes it after the book's gates pass, and a writer never edits it |
| `ops/stack.yml` | the containers `ostler env` runs for this service, with their templates beside it |

Each package has an `ALL` (endpoints, journeys) or `__all__` (fixtures) that registers what
it defines. A class nothing registers does not exist for ostler.

Four books hold the rules, by how far each reaches:

| Book | Holds | Lives in | Written by |
| --- | --- | --- | --- |
| service | what one service does and why: its Python and `decisions/` | `<book root>/services/<repo>/<name>/`, or `<book root>/services/<name>/` with `book.home: repo` | agents |
| product | the product's words, the constraints no story may break, where the truth for a calculation lives | `<artifacts dir>/products/<product>/<slug>.md`, or `product/<slug>.md` beside `services/` with `book.home: repo` | agents |
| team | how one team builds across products: ADRs, RFCs, conventions | `<artifacts dir>/teams/<team>/<slug>.md` | people |
| company | rules every team follows | `<artifacts dir>/company/<slug>.md` | people |

The product is `book.product` in the repository's `agents.yml`, else the repository's name. The team is `book.team` in the repository's `agents.yml`, and no team book is read without it. When two books
disagree, the order of authority is company, team, product, service decision, story. Report a conflict and settle
neither side. An agent writes a product page and never a team or company page. `ostler book pages` lists the pages.

A service that answers gRPC calls, or one of several services in a repo that share accounts
and refusals, is written with [references/grpc.md](references/grpc.md) open: it covers the
`Rpc` declaration, status codes by name, proto field names, the `services/shared/` package
and a world of shared records that a cell cannot make its own copy of.

A service that calls another service, such as a gateway or an API in front of a backend,
is written with [references/neighbours.md](references/neighbours.md) open: it covers
`Foreign`, `Needs`, `Passes`, `Reaches` and `OwnerRefused`, and the rule that a book holds no
record, rule or action for what its service does not store.

A web app, driven through a browser, is written with [references/screens.md](references/screens.md)
open: it covers `Screen`, components found by role and accessible name, `Interaction`,
`PageSurface`, how the run judges a page, and the states a screen takes from a backend's book
instead of making its records.

What a play calls on the book, in what order, is in [references/play.md](references/play.md).
Open it when you need to know what a play does to the book, in what order, or why a world was
or was not reset: the reset and the day of a world, the baseline of a journey, the hooks a
surface may offer, where an endpoint's input classes get their base, how twins play, and what
`--only` plays.

A field's shape decides what a run types into it. [references/inputs.md](references/inputs.md) lists
the input classes and twins of each shape, the language they play in and what the run's `inputs:` and
`twins:` lines mean.

A command-line tool is written with [references/commands.md](references/commands.md) open: it covers
`Command`, the argv template, exits, the sandbox, the file watch and what the run compares.

A service reached by more than one surface, say an API and the web app over it, keeps one book.
The model lives once, in `services/<name>/model/`, because a record does not change with the
surface that reaches it. Each surface gets its own `services/<name>/<surface>/service.py`, with
its own surface, endpoints or screens, journeys and `index.tsv`, and ostler loads it as
`services.<name>.<surface>`. In the artifacts folder these paths and modules sit under `<repo>`. A rule two surfaces enforce is one `Rule`, and each surface shows
its refusal in its own words. A service deployed as two pods, such as an API and a queue
handler built from the same code, is one service and keeps one book. The events the handler
hears are declared beside the endpoints and share their model, journeys and decisions.

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
   later step that names a record an earlier step created takes that step's fixture, never its
   id, or a fixture holding it as a field: the id the app answered travels with the object.
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

A book is restructured when a new claim needs it. The first structure is not a contract. A
fact every journey shares is the usual thing to split: a claim that needs it absent gets its
own record, created by the backstage with a run-unique name, and the journeys that rely on it
keep theirs. A pass that changes a shared part of the book is judged by a play of the whole
book, not by the targeted run.

## Backfilling commits

A book follows the app commit by commit. `service.py` names the app's `roots`, the whole source
trees of the service with only tests, mocks, test rigs and seed fixtures ignored, never a
chosen layer: a route lands first in generated code and a contract, a rule in a stored
procedure. The book records the app commit it was verified at.

`ostler book stale services.<name> --app <app root>` is the batch. Each stale
element is an existing endpoint or record to replay. Each changed file or function no element
names is a route or a rule to add, or a `source` pointer to extend down to it; code that no served
request runs goes in the app's `ignore` as `path` or `path::function`, and code a served request
runs, however pure, is named in a `source`. Each decision listed is
one to reread. Work them through "Adding a route", then `verified` records the app's HEAD. An action
and an outside happening name their code with `source` too, so a change in a domain function or a handler that
no endpoint reaches is found. `ostler book affected` turns the same diff into the calls and journeys to play. Done
when `stale` lists nothing. `--app` names the code checkout, one member in a workspace. A pointer into another member is listed as `not traced`.

A first pass over a service works the `missing` list to empty instead: each tracked file under
the app's roots that no element names gets an element with that file in its `source`, or a
pattern in `App(ignore=...)` when no served request runs it. A screen and an
interaction carry `source` like an endpoint does. The writer finds every page, endpoint and
command from the app's code and its `source` backlinks, and no one hands it a list. A progress
report names each screen beside its file and never gives a bare count.

`missing` also names each call a contract lists that no element declares. A `.proto` under the
roots, a proto anywhere in the app that declares a service one of the book's `Rpc` calls names,
and an OpenAPI or Swagger document under the roots each list calls, and a contract counts as named only
when every call is. A call gets an `Rpc` or an `Endpoint`, or an `ignore` pattern when no served
request runs it. A call that streams its request or its answer is declared like any call,
with `streams = "answer"`, `"request"` or `"both"`: `search` and `explain` say it streams, and a run
never plays it.

When the commit answers a story, the story is the intent: read its model, plan and review
answers before the diff, and write the delta from them. The latest decision wins. A review
answer or the commit message that changes what the model said is the intent now, and the
older line is recorded as settled, never as an app defect.

A check that shows the app breaking the intent stays in the book. A red journey is the right
result until the defect is declared known; a journey or probe removed to get green leaves the
defect where no run will notice it being fixed or growing.

## A book of an outside system

Write one for a third-party system the product calls, which you know only from its
documentation and its live behaviour. It has no code in any repository, so it declares no `app`:

```python
service = Service(
    ...,
    documentation=Documentation(sites=("https://vendor.example.com/docs/api",)),
)
```

A service declares `app` or `documentation`, never both. Each element's `source` is the
documentation address of what it states, with the usual `::<anchor>` suffix. `check` holds each
pointer to the declared sites, a prefix match that calls no network, and refuses a file path.
`stale`, `affected` and `missing` print `<name> describes an outside system: no code to compare, a play against the live system shows whether it still holds` and
exit 0. That pass does not say the book is current: nothing was compared. `verified` prints
`not stamped: <name> describes an outside system` and exits 0. The live system proves the book:
play it with `run` against the real service.

## The world every cell runs in

The app is never wiped. Every cell, every journey and every coworker shares the same
standing accounts, so the app holds records the book never made. Write as if the app were
already busy:

- **A cell makes what it acts on.** A scene's steps create the records the column aims at.
  Ids come from the app's answers; a fixture learns its id from the `creates=` answer. Never
  write an id the app issues.
- **A book plays green on freshly loaded data.** A record an earlier play left behind is no
  fixture. A field or a state a play needs is arranged by that play, and what no play can
  arrange is declared `Unseen`. Before the book is done, reload the stack's data and play the
  whole book once more.
  The book states `fresh` on its stack, and the workflow's closing play reloads through it.
  Check the book with `ostler book run <module> --fresh-data` before reporting it done.
  The command returns only once the data is loaded and the application answers.
  It is the cheapest command that restores the loaded state.
- **A list is read as containing.** The runtime compares a list only on the entries whose
  ids the book learned. An entry whose id the book never learned drops out of the comparison,
  and an entry whose id is read as written (`strangers`) stays in it. So the service's own
  records get learned ids, the model keeps no seeded record a call can make, and a cell reads
  only what it made. Assume no list is empty, and assert no count of everything listed.
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
- **`restore()` leaves every record the run did not make as it found it.** It retires,
  deletes, cancels and edits none of them, whatever a list shows, because they belong to
  whoever shares the environment. The two exceptions are worded in
  [references/grpc.md](references/grpc.md): a shared record keyed by a name is put back, and a
  record that keeps acting is ended, each limited to records the run made or the named shared
  ones.
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

Run from the code repository, or from the book root with `--app`, one at a time.
`ostler book branch` opens the book branch of the current code branch and prints its root. `ostler book land` lands it on the artifacts base by rebase and fast-forward, then removes its worktree and branch. Never start a second `run` or `explore` while
one is live.

| Command | Takes | Tells you |
| --- | --- | --- |
| `ostler book check services.<name>` | seconds, no app | the format: unregistered endpoints, journeys or rules, unplaced endpoints, modules nothing imports, missing source pointers, a journey with no docstring, an `index.tsv` older than the book (run `index`, then `check`) |
| `ostler book explore services.<name> --seed-only` | seconds to minutes as matrices grow, no app | the model's walk to depth 4; run it after every change to a fixture, a scene or an endpoint; "the book contradicts itself" means a fixture arranges a record that cannot exist |
| `ostler book explore services.<name> --no-stack --only <A>,<B>` | about 2 s a cell | every cell of the named endpoints, or interactions in a screen book, on every state the walk reaches, against the app |
| `ostler book run services.<name> --no-stack --only <A>,<B>` | a few minutes | the journeys that call the named endpoints or interactions, their declared cells and their input classes, including divergences declared for them and never met |
| `ostler book run services.<name> --no-stack` | tens of minutes | every journey, every declared cell and every input class; the book's gate, run when a backfill ends and nightly, never per batch |

A run prints the section `Stated and never played` before its verdict: each outside happening, action, rule and scene
that no play exercised, with what closes it (a journey step or a given that arranges the happening, a cell built in the
scene, a step or input class that draws the refusal). It is a list and never turns the run red. An action carried only by
an unplayed outside happening is named on the happening's line. The run also writes `<service>-played.json` to the report
folder: each element with the journeys, cells and input classes that exercised it.
| `ostler book move [NAME ...] [--repo REPO] [--from FOLDER] [--to FOLDER] [--dry-run]` | seconds, no app | moves flat books into `services/<repo>/` of the artifacts checkout `--to` names, and rewrites every dotted module name; `--from` moves a whole `services/` folder out of a code repository; lists each `services/<name>/` path to check by hand; `--dry-run` changes nothing |
| `ostler book index services.<name>` | seconds | rewrites `index.tsv`, which `search` reads |
| `ostler book stale services.<name> --app <root>` | seconds, no app | the elements whose source changed since the verified commit, changed files no element names, decisions they touch |
| `ostler book missing services.<name> --app <root> [--under <folder>] [--files]` | seconds, no app | every tracked file under the app's roots that no element names, and every call a contract file lists that no element declares; prints the map of each named file to its elements, the unnamed files, a count per ignore pattern (`--files` lists them) and the undeclared calls; exits 1 for either; the batch a backfill works through |
| `ostler book decisions services.<name> --unexplained [--kind KIND]` | seconds, no app | the class name of each endpoint, record, screen and interaction no decision names, one per line; `--kind` keeps `endpoint`, `record`, `screen` or `interaction` |
| `ostler book verified services.<name> --app <root>` | seconds | records the app's HEAD once `stale` is worked |
| `ostler book affected services.<name> --app <root> [--since <commit>] [--out <dir>]` | seconds, no app | the calls and journeys to play for the code changed since the verified commit or `--since`, uncommitted and untracked work included; plan `none`, `empty`, `partial` or `whole` (`empty`, with exit 1, means files changed and none selects a play), the changed files of the book's own folder read class by class (an edited element class selects its plays, and a changed module-level name, or a changed class that is no element, selects the elements that use it, found through the book's own files; only a changed line that is no class and no name, or a name the walk cannot trace, makes the plan whole), the files outside every root it did not judge under `diff.not_computed`, the `only` and `journeys` lists to pass to `run`, `whole` with its `reason`, the chain from each changed symbol to its element and plays, with how it was reached (`direct`, or `through` the nearest symbol that mentions the change), the changed symbols and paths no element names (exit 1), the ignored ones, the Go import-only files, the widened places (a hunk with no definition line, still a list), and the fallbacks that made the plan whole (a screen no interaction names or an action no call carries goes under `unplayed` and does not widen the plan; a record or an event still makes it whole); writes `<service>-affected.json`; ends with the `run` line to play |

`--only` takes endpoint class names, or interaction class names in a screen book, or outside happening names, never journey names. A wrong name is refused before anything starts. `explore` and `run` print their verdict when they end, and a long one may outlive the shell's
wait. Send the output to a file and read its last lines once the command has exited.
[references/play.md](references/play.md#running-a-long-play) says how to start one and what it prints. Their report goes under
`--out`. Omitted, it goes to a fresh temp folder the command names on a `reports:` line. In a story, point `--out` at the story's spec folder, and never inside a repository. `--no-stack` skips starting the
stack `service.py` declares, and changes nothing when that stack is empty.

An application the book does not start still needs its data reloaded. The stack states how, and `ostler book run <module> --fresh-data` runs that command before any call:

```python
Stack((), log_dir, fresh=Fresh(("make", "seed"), cwd="repo://api-service"))
```

`cwd` takes `repo://<member>/<path>`, an absolute path or a path under the book root, and empty is the book root. A repo that shares its stack through `services/shared/` states the `fresh` there once. A book that states none runs one of two ways. When its environment has an `ostler:` host, `--fresh-data` resets the copy the play uses with `ostler env reset` and prints `data: reloaded by resetting the copy <name> in <N>s`. The copy must be yours: another live holder refuses the reset. With neither a `fresh` nor a copy ostler manages, `--fresh-data` refuses to play and prints `data: not reloaded, the book states no way to reload it and runs on no copy ostler manages: state fresh=Fresh(...) on its Stack`.

A host written `ostler:` in an environment is a copy of the stack that `ostler env` runs. The copy is the
runner's to name: `--copy NAME`, else the lease the run holds, else the name the book wrote after `ostler:`,
else `shared`. Write no copy name the book cannot keep for every runner.

A book in the artifacts folder states no `root` on its `Environment`. The environment reads the stack copy of the code checkout the command runs in. `root` is only for a book kept inside its repository, or for pointing a play at another checkout, and a root derived from the book's own `__file__` lies in the artifacts folder and names no code checkout.

`ostler env up` takes the book's name as its `ops/stack.yml` declares it, the folder under
`services/<repo>/` in the artifacts folder, or under `services/` beside the code, such as `api`, and never the module name. A repository's stack root is the book named `<repo>`. One service of a book is
`book:service`. A wrong name is refused with the list of the books that have a stack file.

`search <term>` and `explain <Endpoint|Journey|Action|Event>` answer what the book already says
before you read any source. A search term may be a label in any of the book's languages, a source file or a part
of its path, or several words in any order. It also reaches a decision by its story id, the classes it explains or
the sources it cites, and an open question by its words with `--kind question`. An event's name finds the event, the actions that emit it and the outside events that hear it, across every book under the root; `--kind event` or `--kind outside` keeps one side. While authoring, `explore` against the app always takes `--only`: the full replay is the
gate's job. The seed-only walk needs no app and runs as often as you like.
