# Adding a route

Reached from [../SKILL.md](../SKILL.md) when you add an endpoint, a screen or a command to a book, or backfill a book over commits it missed.

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
targeted replay and the targeted run are at 0 fail.

The full `run` plays the whole book, and its time grows with every route. It is the book's
gate, not the batch's: it runs once when a backfill ends and once a night after that. A `FAIL`
there is a batch that left an endpoint out of its targeted run, so the fix names that endpoint
in the next targeted run.

A book is restructured when a new claim needs it. The first structure is not a contract. A
fact every journey shares is the usual thing to split: a claim that needs it absent gets its
own record, created by the backstage with a run-unique name, and the journeys that rely on it
keep theirs. A pass that changes a shared part of the book is judged by a play of the whole
book, not by the targeted run.

### Backfilling commits

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
