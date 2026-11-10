# The surface: endpoints and shapes

Reached from step 4 of adding a route in [../SKILL.md](../SKILL.md).

## An endpoint

One class per route. The class body declares, and an instance is one call. It has no method
of its own.

```python
class ReadTodo(Endpoint):
    method = "GET"
    path = "/todos/{id}"
    auth = CREDENTIALS
    params = Object(id=Field(Id(TodoRecord), does="the todo's id"))
    answers = (Answer(200, TODO, "the todo, with its status as of the service's today"), NOT_FOUND, NO_CREDENTIAL)
    does = "Reads one todo."
    source = ("api/internal/app/controllers/todo_controller.go::TodoController.Get",
              "api/internal/core/services/todo_service.go::TodoService.Get")
    carries = actions.ReadTodo
```

- `params`, `query`, `body` and `headers` are `Object`s. The runtime fills the path
  parameters and the query from the fixture the call is given, field by field, by name. An
  endpoint with both a path parameter and a query takes one fixture that carries both. An
  endpoint whose only input is a query, such as a top-level list, takes it as `query=`.
- `answers` lists every status the route can give. A status the app answers and the list
  lacks is a FAIL; a listed status no run sees must be declared unseen.
- `source` points at the handler first, then the code it reaches, as `path::Symbol`. `stale`
  reads these to say which elements a commit touched, so a pointer that names the shared
  procedure or library function is what makes a coworker's change findable.
- `does` is one or two sentences a caller would read. Behaviour the openapi leaves out goes
  here.
- `refusals` overrides the service's refusal keys for this endpoint only.
- The endpoint registers in its module's `ALL`, and `endpoints/__init__.py` collects them.

A call: `ReadTodo(fixture, by=OWNER)`. `by=None` sends no credential. `auth=ApiKey()` picks
another credential. `body=` sends a body other than the fixture. `query=` sends a query
fixture to an endpoint that has no path parameter. `makes=Fixture()` gives a create that copies a record, such as a clone, the
fixture that learns the new id.

A query is declared on the class like the params:

```python
class FindTodos(Endpoint):
    method = "GET"
    path = "/todos"
    query = Object(
        text=Field(Str(), required=False, does="matches title or description, case folded"),
        status=Field(Enum(STATUSES), required=False),
    )
```

## Answers

`Answer(status, shape, means, creates=None, why="")`. `means` says when the app gives it.
`creates="id"` names the field the fixture learns as its id. `why` explains an answer that
looks wrong but is the app's behaviour, such as a 500 a malformed id earns.

## Shapes

Declare each body once in `endpoints/shapes.py` and reuse it.

- `Object("Name", field=Field(...), ...)`. `Field(shape, required=True, nullable=False,
  does="", opaque="")`. `opaque="<why>"` marks a field the model cannot predict, such as a
  server timestamp; the runtime checks its type and skips its value. On a field that may be
  absent or null, it still compares whether the field is set, against the model view's
  attribute of that name (or `reads`), with None meaning unset. A `lastSentDate` stamped by
  the service's clock is opaque, and an order the model keeps unsent still fails the run if
  the app lists a date. So the view's attribute answers None exactly where the app leaves the
  field empty. A placeholder value fails every row the app leaves empty.
- `Str(format=..., max_len=...)`, `Int()`, `Num()`, `Bool()`, `Enum(values)`, `Bytes()`,
  `Map(of)`, `List(of, unordered="")`.
- `Id(kind, of=Str(format="uuid"), strangers="", minted="")`: an id of a record kind. The
  runtime maps the app's ids to the model's. `of` is the id's own shape: `Str(format="uuid")`,
  `Str(format="hex32")`, `Str(format="ulid")`, or a plain `Str()` when the app checks no
  form. Give the form the handler checks: the runtime sends one character short, one too
  many and one outside the alphabet, and the model's refusal for a malformed id judges each.
  Who makes the id decides which form it takes, and one `Id` names one maker:
  - The service issues it, in any form (a uuid, `AS-15`): `Id(Record, <its wire shape>)`, and
    the fixture learns it from the answer that `creates=` names.
  - A person chose it, or another service issued it and this book only types it (a handle, a
    team someone named, another service's ticket): `strangers="<why>"` makes the runtime read
    back a value the book never issued as written.
  - The value must be unique in the environment and the book supplies it (a tag, an email, a
    team only one cell uses): `minted="<why it must be unique>"`. The book writes a stable
    name, the runtime sends that name with a dash and eight hex characters, and every answer,
    step text and report shows the stable name.
- `Object(...).one_of("a", "b")` when the handler takes exactly one of two fields, and
  `.together("a", "b")` when it takes both or neither. The runtime sends the body with
  neither, with all, and with each one alone, and the model's rules judge each.
- `List(shape, unordered="<why>")` when the app leaves ties in an order the book cannot
  predict. Without it, order is compared.

## Refusal keys

`Service(refusals=Refusals(...))` names what the app answers to each class of wrong input
the model has no rule for: `malformed`, `wrong_type`, `unknown_id`, `wrong_kind`, `missing`.
Each is a `Refusal(message, status)`. An input class predicts its refusal through these keys,
so a route that answers differently overrides them on the endpoint.

## Outside events

A record only the outside world creates, such as a mail reaching a supplier or a stock
feed, is arranged by an `Arrange` subclass, not by an endpoint a caller sends:

```python
class Lands(Arrange[Order]):
    does = "An order reaches a supplier by mail."
    carries = actions.Land
```

It goes in `Service(outside=...)`, and the backstage performs it. A new endpoint on a record
an outside event also arranges gets a fixture of its own; an existing fixture's examples are
never widened to suit it.
