# The book on disk and in Python

Status: plan derived from `docs/design/book-from-scratch.md`. The three todo
books in `~/Documents/ai-artifacts/scratch/golden-books-design/services/` are
the worked example every section cites. Nothing here has landed in stablemate.

## 1. Who feels this

The agent in a run searches the book for what a request does and finds prose.
The book writer repairs pages the checker calls malformed while the app says
something else. Both get the same thing from this plan: one Python module per
service that ostler runs against the app and renders into the pages the agent
reads.

## 2. Layout

One folder per service. Each is a Python package that imports `ostler.book`
and the standard library only.

```
services/
  api/
    service.py          Service[TodoApp]: the one object ostler loads
    surface.py          TodoApi: sends an Endpoint call, returns Done or Refusal
    model/
      state.py          TodoApp, Serving, StoreDown; UNAUTHORIZED, SERVICE_UNAVAILABLE
      todo.py           TodoRecord, record(fixture), the derived status
      rules.py          title_required, title_too_long, not_found, ...; FIELD_RULES
      actions.py        AddTodo, ReadTodo, ReplaceTodo, RemoveTodo, FindTodos, TellDay, MoveClock, SwitchStore, Wipe
      lifecycle.py      CHORE_SCENES, CHORE_ACTIONS, APP_SCENES, APP_ACTIONS, MATRICES
    endpoints/
      shapes.py         TODO, TODO_INPUT, ERROR, CLOCK, STORE
      todos.py          one Endpoint class per route under /todos
      admin.py          SetClock, SetStore, Wipe
    fixtures/
      todo.py           Todo dataclass; todo(), scheduled(), past_due(), assigned(), blank_title(), stranger()
      query.py          Query
      admin.py          Clock, Switch
    journeys/
      a_week_of_chores.py
      clear_the_list.py
      the_day_passes.py
      the_store_is_down.py
      wrong_turns.py
  web/
    service.py          Service[TodoApp] with screens and interactions
    surface.py          TodoWeb: performs an Interaction in the browser
    backend.py          points at services/api/endpoints, which own the routes
    interactions.py     AddTodo, EditTodo, RemoveTodo, Filter, DayPasses, SetStore, SetNetwork
    screens/
      labels.py         T("Search", "Rechercher") and the rest
      list_page.py      ListPage: components, stored, phases, transitions
      add_form.py  edit_form.py  remove_dialog.py
    model/              the same shape as api/model, with Online, Offline, StoreDown
    fixtures/           todo.py, query.py, hooks.py
    journeys/           eight, including offline_shows_the_last_list.py and every_label_reads_in_french.py
  mobile/
    the same as web, with screens/{list_screen,add_screen,todo_screen,remove_dialog}.py
```

Rules the layout enforces:

- Each service holds its own model copy. The web book does not import the api
  book's model. The web book's `backend.py` points at the api endpoints because
  the api owns the routes, and that is the only cross-service reference.
- Fixtures sit in `fixtures/`, nowhere else. A journey builds its data from a
  factory there.
- A journey is one file, one class, one docstring, one `steps`.
- Markdown beside the package says what the service is for and points at the
  module that owns each fact. It restates nothing.

## 3. The model

The model is a reducer. A state holds collections. An action takes a fixture
and a state and returns what to apply. The state applies it and keeps a trace.

### State

```python
class TodoApp(State):
    todos = Collection(TodoRecord, Unique("id"), Index("assignee"))

    def rows(self) -> tuple[Row, ...]: ...
```

`today` is on every `State`. A collection declares each index it has. A mode
of the app is a subclass with its own rules:

```python
class Serving(TodoApp):
    rules = (UNAUTHORIZED,)

class StoreDown(TodoApp):
    rules = (UNAUTHORIZED, SERVICE_UNAVAILABLE)
```

### Action

```python
class StoreAction(Action[A, TodoApp], Generic[A]): ...

class AddTodo(StoreAction[Todo]):
    accept = Todo
    rules = rules.FIELD_RULES

    @staticmethod
    def reduce(a: Todo, s: TodoApp) -> Transaction:
        a.set(id=str(uuid4()))
        return Transaction(Create(s.todos, record(a)))

class FindTodos(StoreAction[Query]):
    accept = Query
    rules = (rules.unknown_status,)

    @staticmethod
    def reduce(a: Query, s: TodoApp) -> Select[TodoRecord]:
        return Select(s.todos, where=matches(a, s.today), order=listing_order(s))

class MoveClock(Action[Clock, TodoApp]):
    def reduce(a, s): return MoveToday(rules.as_date(a.today))

class SwitchStore(Action[Switch, TodoApp]):
    def reduce(a, s): return Become(StoreDown if a.down else Serving)
```

`StoreAction` marks the actions that reach the store. The state rule
`SERVICE_UNAVAILABLE` refuses any of them while the app is `StoreDown`, and
lets `SwitchStore` through.

### Rule

```python
title_required = Rule[Todo, TodoApp]("Title is required", lambda a, s: not a.title or not a.title.strip())
due_not_in_the_past = Rule[Todo, TodoApp]("Due date cannot be in the past", lambda a, s: ..., 400)
not_found = Rule[Todo, TodoApp]("Not found", lambda a, s: a.id not in s.todos, 404)
FIELD_RULES = (title_required, title_too_long, description_too_long, due_must_be_a_date, due_not_in_the_past, no_such_user)
```

`State.dispatch(request)` runs the surface element's gates, then the state's
rules, then the action's rules in tuple order. The first broken rule is the
refusal. `FIELD_RULES` is in field order, so the endpoint's note "the first
one, in field order" is a fact of the tuple, not a promise.

### Derived values

The status of a todo (overdue, scheduled, unscheduled) is computed from
`due_on` and `today` in `model/todo.py`. The listing order (overdue soonest,
scheduled soonest, unscheduled newest) is `listing_order(s)` in the same
module. Neither is stored, so `MoveClock` changes both without a write.

### Matrices

```python
CHORE_SCENES = (
    Scene("(none)", "no todo is listed", lambda today: ()),
    Scene("unscheduled", ..., lambda today: (AddTodo(todo()),)),
    Scene("scheduled", ..., lambda today: (AddTodo(scheduled(today)),)),
    Scene("overdue", ..., lambda today: (AddTodo(scheduled(today)), SetClock(Clock(today=later)))),
)
CHORE_ACTIONS = {"add": ..., "update title": ..., "update due to a past day": ..., "remove": ..., "on: the due day passes": ...}
MATRICES = (
    Axes[TodoApp]("chore", TODAY, CHORE_SCENES, CHORE_ACTIONS, chore_status),
    Axes[TodoApp]("app", TODAY, APP_SCENES, APP_ACTIONS, lambda m: type(m).__name__),
)
```

`matrix` reaches each scene from a fresh model, applies each action, and
writes the cell: `→ <state> · <primitives>`, `refuse <status> <message>`,
`no-op`, or `impossible` when the scene has no record for the action. The
exercise's chore table is identical for api, web and mobile. The app table
differs: `Offline` exists only where a screen can lose the network.

## 4. Surfaces

### Endpoints

```python
CREDENTIALS = (Bearer(), ApiKey())
NO_CREDENTIAL = Answer(401, ERROR, "no accepted credential")
STORE_DOWN = Answer(503, ERROR, "the store is down")

class AddTodo(Endpoint):
    method = "POST"
    path = "/todos"
    auth = CREDENTIALS
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

Shapes:

```python
TODO = Object("Todo",
    id=Field(Str(), does="assigned by the service, a UUID"),
    title=Field(Str(max_len=120)),
    description=Field(Str(max_len=1000), optional=True),
    due_on=Field(Str(format="date"), optional=True),
    assignee=Field(Str(), optional=True),
    status=Field(Enum(STATUSES), does="derived from due_on and today"))
```

An endpoint has no method. `auth = ()` is a public endpoint. A tuple of
several credentials means any one of them is accepted. The runner compares
every answer's status and body against `answers`: an undeclared status is
`Undeclared`, a body off its shape is `OffShape`, both fail the step.

### Screens and interactions

```python
class ListPage(Screen):
    route = "/"
    components = (Text("list-search", T("Search", "Rechercher")), Select(...), Spinner(...),
                  Button("row-edit", T("Edit", "Modifier"), per_row=True), Banner("offline-banner", ...))
    stored = (Stored("rows", "the last list the server returned"), ...)
    phases = (loading, empty, ready, offline)
    transitions = (
        Transition(loading, When("200 with rows"), ready, then="rows replaced"),
        Transition(ready, When("change list-search"), ready, then="refetch within 200 ms"),
        ...)

class AddTodo(Interaction[Todo]):
    screen = AddForm
    does = "fills the add form and presses Save"
    carries = Add

class DayPasses(Interaction[Clock]):
    screen = None
    carries = MoveClock
```

An interaction is the UI's endpoint: a screen, what it does, what it carries.
A screenless interaction carries a chore the user does not perform: the clock,
the store, the network.

### The surface adapter

`surface.py` is the only imperative code in a book. It dispatches on the step:

```python
match step:
    case AddTodo(): ...fill the form, press Save, wait for the POST and the new row
    case Listed(): ...read the rows shown
```

It keeps a snapshot of what is shown, keyed by fixture id, and waits on a
request or a row. It never waits on time. An app refusal comes back as
`Refusal(message, status)`, and a screen with no status sends `0`, which the
runner matches by message.

## 5. Fixtures

```python
@dataclass(eq=False)
class Todo(Fixture):
    title: str
    description: str | None = None
    due_on: str | None = None
    assignee: str | None = None
    id: str | None = None

TITLE_MAX = 120

def todo(title="Water the plants", **fields) -> Todo: return Todo(title=title, **fields)
def scheduled(today, days=1, **fields) -> Todo: return todo(due_on=plus(today, days), **fields)
def past_due(today, **fields) -> Todo: return todo(due_on=plus(today, -1), **fields)
def assigned(who, **fields) -> Todo: return todo(assignee=who, **fields)
def described(text, **fields) -> Todo: ...
def blank_title() -> Todo: return todo(title="   ")
def too_long_title() -> Todo: return todo(title="x" * (TITLE_MAX + 1))
def stranger() -> Todo: return todo(id=str(uuid4()))
```

A fixture is the shape the journey sends. It carries no id until the app's 201
sets it, through `Answer(..., creates="id")`. An update sends the whole record
with the id. `stranger()` is an id the app never issued, which is how
`not_found` is reached without a hardcoded value. `record(fixture)` in
`model/todo.py` maps the wire shape to the internal record; the two are
different classes on purpose.

## 6. Journeys

```python
class AWeekOfChores(Journey):
    """Ana fills a week, hands one chore to Bo, and clears what is done."""

    def steps(self, today):
        milk = scheduled(today, days=1, title="Buy milk", assignee="ana")
        plumber = scheduled(today, days=3, title="Call the plumber")
        photos = todo("Sort the photos")
        yield AddTodo(milk)
        yield AddTodo(plumber)
        yield AddTodo(photos)
        yield Listed(milk, plumber, photos)
        yield UpdateTodo(plumber.set(assignee="bo"))
        yield RemoveTodo(milk)
        yield ReadTodo(plumber)
        yield FindTodos(query=Query(assignee="ana"))
```

A step is a surface call, `Listed(...)` for the rows the surface should show
in order, `Check(label, probe)` for a fact only the surface knows, or a
`Given` with its `Undo`:

```python
OFFLINE = Given(SetNetwork(Network(offline=True)), undo=SetNetwork(Network(offline=False)))

def steps(self, today):
    yield AddTodo(chain)
    yield AddTodo(bike)
    yield OFFLINE
    yield Check("the offline banner is shown", lambda s: s.banner_shown())
    yield Listed(chain, bike)
    yield Check("Save is disabled", lambda s: s.disabled(s.add_save))
    yield Undo(OFFLINE)
    yield AddTodo(lamp)
    yield Listed(chain, bike, lamp)
```

The runner feeds each step to the model and to the surface, compares the two
answers, and writes one row:

```
| 1 | POST /todos {"title": "Buy milk", ...} | ok | create todos Buy milk [9c4eadff] · due 2026-11-06 · for ana | ok | Buy milk · scheduled · due 2026-11-06 · for ana |
| 8 | PUT /todos/{id} ... | refused 400 Due date cannot be in the past | refused 400 Due date cannot be in the past | ... |
```

A disagreeing row is the finding. The model dump at the end
(`Serving · today 2026-11-05 / todos (2) ...`) is what the agent reads to know
the app's state after the journey.

## 7. Service and stack

```python
def stack(log_dir):
    return Stack((Process("api", ["go", "run", "."], APPS / "api", 8080, {"TOKEN": ..., "API_KEY": ...}),), log_dir)

service = Service[TodoApp](
    name="api", new_model=Serving, surface=TodoApi, journeys=JOURNEYS,
    stack=stack, endpoints=ENDPOINTS, matrices=MATRICES,
    words={"todo": "one chore with a title and an optional due day", ...})
```

A screen book passes `screens=SCREENS, interactions=INTERACTIONS` instead of
`endpoints`, and its stack starts the api and the UI server. `--no-stack` runs
against processes already up.

## 8. What ostler provides

| Command | Reads | Writes |
| --- | --- | --- |
| `ostler book run <svc>` | journeys, surface, model | `results/<svc>.md`, one row per step, model dump |
| `ostler book matrix <svc>` | matrices, model | `results/<svc>-matrix.md` |
| `ostler book graph <svc>` | the matrix cells | `results/<svc>-<axes>.dot` and `.svg` |
| `ostler book endpoints <svc>` | endpoints, shapes, carried actions | `results/<svc>-endpoints.md` |
| `ostler book screens <svc>` | screens | `results/<svc>-screens.md` |
| `ostler book walk <svc>` | journeys | `results/<svc>-walk.md`, the steps as prose |
| `ostler book denied <svc>` | endpoints, surface | each credential dropped once per endpoint |
| `ostler book plan <svc>` | endpoints, shapes, model | each body field valid and invalid, each path param at every entity and one unknown id |

The runtime is `ostler/book/`, about 2500 lines: `domain`, `state`, `model`,
`outcome`, `http`, `screen`, `journey`, `service`, `stack`, `surface`,
`runner`, `matrix`, `graph`, `explore`, `denied`, `planner`, `browser`, `cli`.
`browser.py` imports Playwright optionally; it is the one import outside the
standard library, and only a screen book's surface reaches it.

Timings from the exercise, with the stacks already up:

| Book | Journeys | Wall time |
| --- | --- | --- |
| api | 5 | under 5 s |
| web | 8 | about 8 s |
| mobile | 8 | about 100 s |

Mobile is slow because Flutter web exposes semantics lazily. The book does not
wait on time anywhere; it waits on the row.

## 9. Walkthroughs

### A story adds a transition

The story lets a todo be reassigned to nobody. The writer:

1. Adds a rule or relaxes one in `model/rules.py`. Here `no_such_user` learns
   that an empty assignee is allowed.
2. Runs `ostler book matrix`. The "update assignee to nobody" column was not
   there, so the writer adds it to `CHORE_ACTIONS` and runs again. The cells
   fill from the reducer.
3. Adds a step to a journey, or a journey, in `journeys/`.
4. Runs `ostler book run`. Every row agrees, or one does not and names the
   step.
5. Runs `ostler book endpoints` and `graph`. The pages and the svg are
   regenerated. No markdown is edited by hand.

### A shared fixture changes

`TITLE_MAX` moves from 120 to 80. `too_long_title()` follows, because it reads
the constant. `title_too_long` in `rules.py` reads it too. `plan` tries 81
characters and expects 400. The api must agree or the row says where it does
not. Three books each hold the constant, so the writer changes it three times,
and the identical chore matrix across the three is the check that none was
missed.

### A screen loses the network

Only a screen book has `Offline`. The writer adds `Offline(TodoApp)` with the
`OFFLINE` rule, a `SetNetwork` interaction with no screen, a `Network` fixture,
and a journey that wraps steps in `Given(SetNetwork(...), undo=...)`. The app
matrix gains an `Offline` row. The api book is untouched.

## 10. Slices

| | Slice | Files | Done when |
| --- | --- | --- | --- |
| S1 | Runtime into ostler | `ostler/book/*` copied from the exercise; `ostler/pyproject.toml` optional dependency `browser = ["playwright"]` | `make lint` clean except the optional import. `ostler book run services.api` passes from stablemate with `PYTHONPATH` on the exercise. |
| S2 | CLI | `ostler/cli.py` gains the `book` group with run, matrix, graph, endpoints, screens, walk, denied, plan | Each writes what `results/` holds today. |
| S3 | Loader | `ostler/book/loader.py`: find `service.py` under `docs/services/<svc>/book/`, import it, hand `service` to the command | No `PYTHONPATH`. A book is named by its service. |
| S4 | Doctor | an import check (only `ostler.book` and the standard library), a stamp of `code:` bullets that cite a book module | A book that imports pytest fails doctor. A changed `actions.py` shows as stale on the page that cites it. |
| S5 | First production book | `docs/services/ostler/book/` for the stablemate CLI, with a `Command` surface element designed in this slice | Its chore matrix renders and its journeys run against `ostler` itself. |

Each slice lands on its own. S1 and S2 can run together in one branch since S2
has nothing to call without S1. S5 is the first slice that touches a product
book, and the `Command` surface is the one design decision this plan leaves
open: the exercise had no CLI service.

## 11. Departures from the design note, and open decisions

- The design note's S3 reads "discovered from `docs/services/<svc>/book/service.py`".
  This plan puts the book under the service's existing folder so `ostler search`
  keeps finding the page that points at it. Settled here.
- The runtime stays one package, `ostler.book`. The exercise's modules are flat
  and about 2500 lines together. Splitting it waits until a second product book
  shows which seams matter.
- `Command` for CLI surfaces: open until S5. The shape will mirror `Endpoint`
  (argv, environment, exit codes with their output shapes, `carries`).
- Doctor's import check: a grep of `import` lines under the book folder. A
  book that needs a third-party client for its surface declares it in the
  service's `pyproject`, and doctor allows what that file lists. Open whether
  the allowance is per service or per book; per service is the recommendation.
