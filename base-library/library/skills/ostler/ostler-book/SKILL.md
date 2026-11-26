---
name: ostler-book
description: "Writing a service's book, the Python model ostler replays against the app: endpoints, screens, states, journeys, fixtures. Load when editing anything under a book's services/<name>/, fixing a check or run finding, or backfilling routes."
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
  the app's own tests, and a driver waits on an event the app emits, never on a timer. The one
  concurrency the book meets is a call the app asks to send again, below.

## A call the app asks to send again

An app may refuse a call with a signal its contract documents as "send it again": a conflict
status whose message says the record changed, a 409 that names a stale version, a 503 with
`Retry-After`. Any real client of the app sends again on that signal, so the book's client does.

- The retry lives in the client's `transport`, so every step, cell, arrangement and watch read
  sends the same way. [references/retry-on-conflict.md](references/retry-on-conflict.md) holds the shape.
- It fires on that exact signal, status and message together, for a few attempts, and then the
  last answer stands.
- It never sleeps. A `Retry-After` is the one wait allowed, for the time the app names, and
  only where the client can read it: `transport` sees the status and body, not headers.
- A file under `decisions/` names the race and the signal, with `elements:` listing the client.
- A refusal the app does not document as retryable is never retried. It is an app finding for the
  report, like any other divergence.

A play that passes only some of the time points to a race. Before the book's final commit, play it
three times, reseeding between plays when the book has a reseed. When a result changes between
plays, find the call that differs. The app's documented signal on it means the rule above applies.
No such signal means an app finding, reported and never masked.

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
its own surface, endpoints or screens, journeys, and ostler loads it as
`services.<name>.<surface>`. In the artifacts folder these paths and modules sit under `<repo>`. A rule two surfaces enforce is one `Rule`, and each surface shows
its refusal in its own words. Each surface reads `decisions/` and `QUESTIONS.md` from its own
folder and from `services/<name>/`, beside the model. A decision there may name the elements of
every surface, and a decision in a surface's folder names only that surface's. A service deployed as two pods, such as an API and a queue
handler built from the same code, is one service and keeps one book. The events the handler
hears are declared beside the endpoints and share their model, journeys and decisions.

## Adding a route

Adding a route, and backfilling a book over commits it missed, follow the steps in [references/adding-a-route.md](references/adding-a-route.md). Open it before you add an endpoint, a screen or a command.
Its steps send you to [references/model.md](references/model.md) for records, actions and rules, [references/surface.md](references/surface.md) for endpoints and their answers, [references/matrices-and-journeys.md](references/matrices-and-journeys.md) for matrices, fixtures and journeys, and [references/findings.md](references/findings.md) for what each finding of a replay means.

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

Run one command at a time, and never start a second `run` or `explore` while one is live. What each command takes and tells you, and how `search` and `explain` answer before you read source, are in [references/running.md](references/running.md). Open it before the first command of a session.
