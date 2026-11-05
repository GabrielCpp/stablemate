# The book, redesigned from what agents failed at

Status: design settled by the exercise in
`~/Documents/ai-artifacts/scratch/golden-books-design/`. Three books (api, web,
mobile) run green against the todo apps there. No stablemate code has moved
yet; the plan in `docs/plans/book-layout-and-scenarios.md` says how it does.

## 1. Problem

An agent that holds only the book has to operate the app and say why it
behaves as it does. The book today is markdown with a bullet grammar that a
checker reads back. The reader who feels the gap is the agent in a coder or QA
run: it searches the book, finds prose that describes a surface, and still has
to read the source to learn what a request does to the data in each state. The
operator pays for that in tool calls and in repairs of pages that drifted from
the app.

Three blockers came out of the tool-call audit of the book runs:

| | Blocker | What the agent did instead |
| --- | --- | --- |
| B1 | The book states behaviour in prose, so nothing checks it. | Read the source to be sure. |
| B2 | A page describes one surface; the state the surface changes lives nowhere. | Re-derived the state from several pages, wrongly. |
| B3 | The checker verifies the page's form, not its claims against the app. | Repaired pages that were well-formed and false. |

The incidents behind them all share one shape: a sentence in the book that a
running app could have contradicted and nothing ever asked it to.

### What done looks like

| Need | Done when |
| --- | --- |
| Behaviour stated once | One reducer per service says what each action does to each record in each state. |
| Behaviour checked | Running the book drives the app and compares every step against the reducer. |
| Surface complete | An endpoint page carries no less than an OpenAPI document would. |
| Readable by the agent | Prose points at the Python. Nothing is stated twice. |
| Rendered | Ostler draws the state table and the state machine from the reducer, never from a hand-drawn figure. |

### Out of scope

Restarts and concurrent clients. The reducer models a single client against an
in-memory service. The incidents that motivated this were all single-client.

## 2. Claims

The exercise re-derived these from the earlier draft. Each one is either shown
by the running books or dropped.

| | Claim | Status |
| --- | --- | --- |
| C1 | A service is independent. It has its own journeys, its own surface, its own model. | Held. `services/<name>/` is self-contained; the web book never imports the api book. |
| C2 | The model is a reducer. A request resolves to a transaction over collections or to a refusal. | Held. `Action.reduce` returns `Transaction`, `Select`, `Show`. Nothing mutates. |
| C3 | A state of the app is a class. Being down is a state, not a flag. | Held. `Serving`, `StoreDown`, `Online`, `Offline` are `State` subclasses with their own rules. |
| C4 | A surface element has no behaviour of its own. It declares what it carries. | Held. An `Endpoint` declares method, path, auth, body, answers, and the action it carries. It has no method. |
| C5 | Every answer the app can give is declared with its status and its body shape. | Held. The runner refuses an undeclared status (`Undeclared`) and a body off its shape (`OffShape`). |
| C6 | Fixtures are the external shape, in their own folder, composable. | Held. `fixtures/todo.py` has a base factory and variants. The id is learned from the 201. |
| C7 | A journey calls the surface it tests, never a generic verb. | Held. Steps are `AddTodo(milk)`, not `Find`/`Update`. |
| C8 | The book is event driven. No timer, no timeout. | Held. Surfaces wait on a request or a row. |
| C9 | The matrix is computed from the reducer, not written. | Held. `Axes` + `Scene` give cells. `graph` draws them. |
| C10 | The book uses no library outside ostler and no test runner. | Held. A book imports `ostler.book` and the standard library. |
| C11 | Prose does not restate the Python. | Held. The book's markdown points at the module that owns the fact. |
| C12 | The runner derives the refusals to try from the declarations. | Held. `explore.py` walks each body field, each path parameter, each credential. No candidate list in the book. |
| C13 | The book is pytest, one conftest per app, JUnit out. | Dropped. The operator rejected it: too far from the domain, annotation-heavy, a library outside ostler. |
| C14 | Records are declared with decorators on functions. | Dropped with C13. |

## 3. Parts and concepts

### Level 1

| Part | Owns | Must never know |
| --- | --- | --- |
| Model | The states, the collections, the actions, the rules. The one source of behaviour. | Any surface, any transport, any screen. |
| Surface | How a request reaches the app: endpoints for an API, screens and interactions for a UI, commands for a CLI. | What the action does. It names the action it carries. |
| Fixtures | The external shape of a record as a journey sends it. | The internal record. The id comes back from the app. |
| Journeys | A sequence of surface calls with the checks between them. | How a step is driven or compared. |
| Matrices | Which scenes and which actions to tabulate. | What a cell contains. The reducer fills it. |
| Stack | Which processes to start and on which ports. | Anything about the book. |
| Runtime (ostler) | Driving, comparing, exploring, rendering. | Any service. It imports none. |

### Level 2: the model

| Concept | Is | Owned by |
| --- | --- | --- |
| `State` | The whole app at an instant: `today` plus a `Collection` per record. A mode of the app is a subclass with its own `rules`. | `ostler.book.state` |
| `Collection` | A set of records with declared indexes, `Unique("id")` and `Index("assignee")`. One collection may have several. | `ostler.book.domain` |
| `Action[A, S]` | What a request of fixture type `A` does to a state `S`. Declares `accept`, `rules`, `reduce`. | `ostler.book.domain` |
| `Transaction` | The primitives one action applies as a unit: `Create`, `Update`, `Delete`, `Become`, `MoveToday`. | `ostler.book.domain` |
| `Select`, `Show` | A read. Returns rows in a declared order, or one row. | `ostler.book.domain` |
| `Rule` | A message, a predicate over request and state, and a status. State rules run before action rules, in order. The first broken rule is the refusal. | `ostler.book.model` |
| `Entry` | The trace a state keeps of each transaction it applied. The runner reads it to describe a step. | `ostler.book.domain` |

### Level 2: the surfaces

| Concept | Is | Owned by |
| --- | --- | --- |
| `Endpoint` | Method, path, auth tuple, params, query, body shape, answers, `does`, `carries`. No method. | `ostler.book.http` |
| `Answer` | A status, a body shape, a note, and what it creates. | `ostler.book.http` |
| `Object`, `Field`, `Str`, `Int`, `Bool`, `Enum`, `List` | The body shapes. No less than OpenAPI carries. | `ostler.book.http` |
| `Bearer`, `ApiKey` | Credentials. An endpoint accepts a tuple of them, or none. | `ostler.book.http` |
| `Screen` | A route, its components, what it stores, its phases, its transitions. | `ostler.book.screen` |
| `Interaction[F]` | A screen, `does`, `carries`. The UI's counterpart to an endpoint. A screenless interaction carries a chore: the clock, the network, the store. | `ostler.book.screen` |
| `Surface` | The adapter that drives one service's app: sends an endpoint call, or performs an interaction in a browser. The book's only imperative code. | the book, per service |

### Level 2: journeys, fixtures, matrices

| Concept | Is | Owned by |
| --- | --- | --- |
| `Fixture` | A dataclass with `set(**fields)` returning a copy. The base factory and its variants live in `fixtures/`. | `ostler.book.domain` |
| `Journey` | A docstring and `steps(today)` yielding surface calls, `Listed(...)`, `Check(label, probe)`. | `ostler.book.journey` |
| `Given`, `Undo` | A precondition with its reversal: the store down, the network off. | `ostler.book.journey` |
| `Axes`, `Scene` | One matrix: a name, the scenes to reach, the actions to apply, and how to name a state. | `ostler.book.state` |
| `Service[S]` | Name, `new_model`, surface, journeys, stack, endpoints or screens and interactions, matrices, words. The one object ostler loads. | `ostler.book.service` |

## 4. What the book looks like

The api book of the todo exercise, trimmed. The full files are under
`services/api/` in the exercise.

The state and its modes:

```python
class TodoApp(State):
    todos = Collection(TodoRecord, Unique("id"), Index("assignee"))

UNAUTHORIZED = Rule[Endpoint, TodoApp](
    "Unauthorized", lambda call, s: bool(type(call).auth) and call.auth_used is None, 401)
SERVICE_UNAVAILABLE = Rule[Endpoint, TodoApp]("Service unavailable", _reaches_the_store, 503)

class Serving(TodoApp):
    rules = (UNAUTHORIZED,)

class StoreDown(TodoApp):
    rules = (UNAUTHORIZED, SERVICE_UNAVAILABLE)
```

An action:

```python
class AddTodo(StoreAction[Todo]):
    accept = Todo
    rules = rules.FIELD_RULES

    @staticmethod
    def reduce(a: Todo, s: TodoApp) -> Transaction:
        a.set(id=str(uuid4()))
        return Transaction(Create(s.todos, record(a)))
```

A rule:

```python
title_required = Rule[Todo, TodoApp](
    "Title is required", lambda a, s: not a.title or not a.title.strip())
not_found = Rule[Todo, TodoApp]("Not found", lambda a, s: a.id not in s.todos, 404)
```

An endpoint:

```python
class AddTodo(Endpoint):
    method = "POST"
    path = "/todos"
    auth = (Bearer(), ApiKey())
    body = TODO_INPUT
    answers = (
        Answer(201, TODO, "created; the id and the derived status come back", creates="id"),
        Answer(400, ERROR, "a field rule is broken: the first one, in field order"),
        NO_CREDENTIAL,
        STORE_DOWN,
    )
    does = "Creates one todo; the service assigns its id. Two identical posts make two todos."
    carries = actions.AddTodo
```

A fixture and its variants:

```python
@dataclass(eq=False)
class Todo(Fixture):
    title: str
    description: str | None = None
    due_on: str | None = None
    assignee: str | None = None
    id: str | None = None

def todo(title="Water the plants", **fields) -> Todo: ...
def scheduled(today, days=1, **fields) -> Todo: ...
def past_due(today, **fields) -> Todo: ...
def blank_title() -> Todo: ...
def stranger() -> Todo: ...
```

A journey:

```python
class AWeekOfChores(Journey):
    """Ana fills a week, hands one chore to Bo, and clears what is done."""

    def steps(self, today):
        milk = scheduled(today, days=1, title="Buy milk", assignee="ana")
        plumber = scheduled(today, days=3, title="Call the plumber")
        yield AddTodo(milk)
        yield AddTodo(plumber)
        yield Listed(milk, plumber)
        yield UpdateTodo(plumber.set(assignee="bo"))
        yield RemoveTodo(milk)
        yield ReadTodo(plumber)
        yield FindTodos(query=Query(assignee="ana"))
```

A precondition:

```python
given = (Given(SetStore(Switch(down=True)), undo=SetStore(Switch(down=False))),)
```

The matrices:

```python
MATRICES = (
    Axes[TodoApp]("chore", TODAY, CHORE_SCENES, CHORE_ACTIONS, chore_status),
    Axes[TodoApp]("app", TODAY, APP_SCENES, APP_ACTIONS, lambda m: type(m).__name__),
)
```

The service:

```python
service = Service[TodoApp](
    name="api", new_model=Serving, surface=TodoApi, journeys=JOURNEYS,
    stack=stack, endpoints=ENDPOINTS, matrices=MATRICES, words={...})
```

A screen book differs in two places. The surface elements are `Screen` and
`Interaction[F]` instead of `Endpoint`, and the state has a mode the API cannot
reach:

```python
OFFLINE = Rule[Interaction[Any], TodoApp]("You're offline", _reaches_the_store, 0)

class Online(TodoApp):
    rules = ()

class Offline(TodoApp):
    rules = (OFFLINE,)

class AddTodo(Interaction[Todo]):
    screen = AddForm
    does = "fills the add form and presses Save"
    carries = Add
```

What ostler renders from this, with no further authoring:

| Command | Output |
| --- | --- |
| `run` | One row per step: the request, the model's answer, the app's answer, agree or not. |
| `matrix` | The state table per axes: `→ scheduled · update todos Fix the gate [83f4d66a] · due 2026-11-09`, `refuse 400 Due date cannot be in the past`, `no-op`, `impossible`. |
| `graph` | The state machine as dot and svg, from the same cells. |
| `endpoints` | The shapes, then each endpoint with its auth, body, answers and the refusals its action carries. |
| `screens` | Each screen with its components, stored values, phases and transitions. |
| `walk` | The journeys with their steps, as prose. |
| `denied` | Each credential dropped once per endpoint, and what came back. |
| `plan` | Every body field valid and invalid, every path parameter at every entity and one unknown id. |

## 5. Invariants

| | Invariant | Where it is enforced |
| --- | --- | --- |
| I1 | A book imports `ostler.book` and the standard library, nothing else. | Review. `ostler doctor` can grep imports once the books move. |
| I2 | Nothing in the model mutates state. `reduce` returns a transaction; the state applies it. | `State.dispatch` is the only writer. |
| I3 | A mode of the app is a `State` subclass. No boolean on the state says "down". | Type: `Become(StoreDown)` takes a class. |
| I4 | A surface element has no method. It declares what it carries. | `Endpoint` and `Interaction` have class attributes only. |
| I5 | Every status the app can return is declared on the endpoint with its shape. | Runner: `Undeclared`, `OffShape`. |
| I6 | An endpoint declares its credentials as a tuple. Empty means public. Several means any one of them. | `UNAUTHORIZED` reads `type(call).auth`. |
| I7 | A fixture carries no id until the app issues one. Updating sends the whole record. | `Todo.id` defaults to `None`; `Answer(..., creates="id")`. |
| I8 | Fixtures live in `fixtures/` as a base factory and variants. | Layout. |
| I9 | A journey step is a surface call, a `Listed`, a `Check`, a `Given` or an `Undo`. | `Journey.steps` type. |
| I10 | No `sleep`, no timer, no timeout anywhere in a book. | Review. The runtime exposes none. Surfaces wait on a request or a row. |
| I11 | The matrix and the graph are computed from the reducer. Nothing hand-draws them. | `Axes` has no cell field. |
| I12 | The chore matrix is the same across the books of one product; the app matrix may differ. | Observed: identical chore tables, `Offline` only in screen books. |
| I13 | State rules run before action rules; the first broken rule is the answer. | `State.dispatch` order. |
| I14 | One model copy per service. Services share nothing. | Layout: `services/<name>/model/`. |
| I15 | The runtime imports no service. A service imports no other service. | Import direction. |
| I16 | Prose points at the Python that owns a fact. It does not restate it. | Review. |
| I17 | The runner's refusal checks are derived from declarations. The book lists no candidates. | `explore.py`. |
| I18 | A `Refusal` from the app matches the model's by message. Status is compared where the surface has one. | `Refusal(msg, 0)` for screens. |

## 6. Forces and patterns

| | Force | Pattern it produced |
| --- | --- | --- |
| F1 | The agent needs behaviour it can run, not read. | The reducer. Behaviour is Python the runtime executes against the app. |
| F2 | Being down changes every answer. | A mode is a state with rules, not a flag the rules consult. |
| F3 | One collection has several lookups. | `Collection(Record, Unique(...), Index(...))`, not `keyed_by("id")`. |
| F4 | An action touches several records at once. | `Transaction` groups primitives; dispatch applies it or nothing. |
| F5 | The operator expects no less than OpenAPI. | `Endpoint` declares every answer with a shape. The runner enforces it. |
| F6 | The internal record and the wire shape differ. | `Fixture` is the wire shape. `record(fixture)` maps it. |
| F7 | Ids are the app's to assign. | UUIDs; `creates="id"` on the answer; `stranger()` is an unissued id. |
| F8 | Timers hide races and slow every run. | Surfaces wait on a request or a row. The runtime has no sleep. |
| F9 | A hand-drawn figure cannot show an undecided cell. | The matrix is computed; `graph` renders the cells. |
| F10 | A screen has phases an API has not. | `Screen` carries `Phase` and `Transition`; `screens` renders them. |
| F11 | The same chore lifecycle is tested through three surfaces. | Each service holds its own model copy. The chore matrix is the cross-check. |
| F12 | pytest brings fixtures, parametrization and a runner the operator did not want. | `Service` is the one object ostler loads; ostler is the runner. |

The behaviour-model skill's matrix (state × action, with `refuse`, `no-op`,
`impossible`) is what `Axes` computes. The skill's "told apart by" line is the
`status_fn` of the axes. Its "(none)" row is the first `Scene`.

## 7. Mapping onto the existing system

| Today | After | Note |
| --- | --- | --- |
| `docs/services/<svc>/**` markdown with bullets | `services/<svc>/` Python book plus a short markdown that points at it | The bullet grammar carried `does:`, `verify:`, `code:`. `does` moves to a class attribute; `verify` becomes the runner; `code:` stamps move to the plan's slice 4. |
| `ostler doctor` checks form | `ostler book run` checks behaviour; doctor keeps form | Both run. Doctor gains an import check (I1). |
| `verify:` bullets with a check vocabulary | `Answer`, `Listed`, `Check` | The vocabulary's nouns become the runner's comparison. |
| Playwright compile from `interaction` nodes | `Surface` per screen book | Hand-written once per service, driven by `Interaction` declarations. |
| Live audit against the app | `run` is the audit | One runner for the api, the web and the mobile books. |
| `okf-row-vet`, repair loops | Agree/disagree per step in `results/<svc>.md` | A disagreeing row is the finding. |
| `ostler search` over markdown | Unchanged | The markdown pages that remain are the index into the Python. |

### What must not move

| Kept | Why |
| --- | --- |
| `ostler search`, `trace`, `reach` | The agent finds a page by them. The Python book sits behind the page. |
| The `concept` node and its `rule:` bullets | Settled tradeoffs still live in prose. The reducer's `Rule` is a different thing: a runtime refusal. |
| `ostler stamp` | The code bullets that cite app source still need restamping. |
| The sandbox and the stack | `Stack(Process(...))` names processes the existing sandbox starts. |

## 8. Slices

| | Slice | Done when |
| --- | --- | --- |
| S1 | Move `ostler/book/` from the exercise into the ostler package. Type-check clean. | `ostler book run services.api` works from stablemate on the exercise's apps. |
| S2 | `ostler book` subcommands registered on the ostler CLI: run, matrix, graph, endpoints, screens, walk, denied, plan. | Each produces what `results/` holds today. |
| S3 | Loader: `Service` discovered from `docs/services/<svc>/book/service.py`. | A book found by path, not by `PYTHONPATH`. |
| S4 | Doctor: import check, stamp of `code:` bullets that cite a book module. | A book that imports pytest fails doctor. |
| S5 | First production book: the stablemate CLI, through `Command` surfaces. | Its chore matrix renders and its journeys run. |

The plan file holds each slice's files and its order.

## 9. Assumptions

| | Assumption | Standing |
| --- | --- | --- |
| A1 | One client at a time. | Settled. Out of scope above. |
| A2 | The app is in-memory or reset per run. `Wipe` clears it. | Settled. |
| A3 | A screen book's `Surface` uses Playwright through an optional import. | Settled. The only type-check noise in the runtime. |
| A4 | The double-save check (`save_twice_makes_one_todo`) lives in a surface probe. The model has no notion of an in-flight request. | Settled as a judgment. Revisit if a second product needs it. |
| A5 | Mobile runs through Flutter web and is slow (about 100 s for 8 journeys). | Accepted. Flutter semantics, not the book. |
| A6 | The chore matrix being identical across books is the cross-service check. No shared model module. | Settled. One copy per service. |
| A7 | Markdown stays as the index. Prose that restates Python is deleted, not kept in sync. | Settled. |
| A8 | The CLI surface (`Command`) is designed in S5, not before. The exercise had no CLI service. | Open until S5. |
| A9 | Ostler owns `ostler.book`. Books never vendor it. | Settled. |
