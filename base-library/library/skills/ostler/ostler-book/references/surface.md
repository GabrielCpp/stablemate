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

## Credentials

A surface holds every account's credential as a `Signed`, never a bare token. A play outlasts
a token's life, and the input classes of an endpoint hold one arrangement for the whole
endpoint. `Signed` signs the account in on first read and again whenever less than `margin`
seconds of life remain.

```python
self.owner = Signed(lambda: self.back.sign_in("owner"))
self.client.hold(OWNER, BEARER, self.owner)
self.back.api("POST", "/projects", self.owner.token, body)
```

- `sign_in` is the call that signs the account in. It returns the token as a string.
- A JWT carries its own end in `exp`. `Signed` reads it.
- `lasts=` is the life in seconds of a token that is not a JWT. With no `lasts=`, an opaque
  token is never renewed.
- `margin=` is how early to renew, 300 seconds by default.

## Answers

`Answer(status, shape, means, creates=None, why="")`. `means` says when the app gives it.
`creates="id"` names the field the fixture learns as its id. `why` explains an answer that
looks wrong but is the app's behaviour, such as a 500 a malformed id earns. An endpoint
declares each status once. A status the app gives in two forms, such as a 401 with a detail
and one without, is one shape whose differing field is optional.

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
    A blank is sent blank and a value at a declared length bound stays at it, so the field keeps
    its input classes. The same name in capitals or in lower case is the same value in that
    case. A name is one record for the whole run: two journeys that each create one write two
    names. A name is kept per kind, so two fields that must carry the same value, such as a
    tag and the query that searches for it, are ids of one kind. A part of a minted name, such
    as its first letters, cannot be written.
    Mint every record a journey or a fixture creates, not only a name the app requires to be
    unique. The play then finds its records by searching or filtering for that word, or by
    opening them by id. It never reads a whole list to find one record, and it never claims
    the count of a list other users write to. A stack is rarely empty: other books' plays,
    other users and earlier runs leave records behind. Where a list has no search and no
    filter, and its count is the only thing to observe, declare that answer `Unseen` with
    its `Because` and why.
- `Token("<name>")`: a page token, or any cursor the app issues and takes back. The runtime
  compares it by presence and never by value. An answer is right when the app gives a token
  exactly where the model's view gives one. In a request, the runtime sends the app's own
  token in place of the model's.
  The model pages its own list and returns its own token. A fixture helper builds a request
  token from the model's paging function, and no book writes one as a literal. A token in a
  request needs an answer that issues the same name, and the check reports one that none
  issues. Lists whose tokens the service makes the same way share one name.
  The runtime sends a made up token by itself, and the model's refusal judges it. A journey
  spends no step on one.
  A list the model cannot hold whole keeps a `Str` token with `opaque=`, in a shape of its
  own. A standing account's list is one: earlier runs left records there, so the model cannot
  say whether a next page exists. An endpoint that passes the call on to another service
  learns no token yet, so its token stays opaque too.
- `Object(...).one_of("a", "b")` when the handler takes exactly one of two fields, and
  `.together("a", "b")` when it takes both or neither. The runtime sends the body with
  neither, with all, and with each one alone, and the model's rules judge each.
- `Itself("Name")` when a field holds the object that encloses it: a formula whose operands are
  formulas, a folder of folders. Write the tree as one named object and never as one object per
  level (`Expression4` down to `Expression0`), which states four levels and no more. The check
  accepts any depth the app answers and judges every level by the same fields. Each field of the
  tree is one path in the witness, so `ast.value` is seen once whichever level held it. An
  `Itself` whose name matches no enclosing object fails `ostler book check`.

  ```python
  EXPRESSION = Object(
      "BundleExpression",
      kind=Str(), value=Field(Str(), required=False),
      operand=Field(Itself("BundleExpression"), required=False),
      left=Field(Itself("BundleExpression"), required=False),
      right=Field(Itself("BundleExpression"), required=False),
  )
  ```
- `List(shape, unordered="<why>")` when the app leaves ties in an order the book cannot
  predict. Without it, order is compared.
- `List(shape, entries=(has("id"), no_repeat("id"), in_order("name")))` when every entry of the
  list the app answers holds a rule, whoever made the record. A rule judges the whole answer,
  other people's entries included, before the comparison drops an entry whose id the book never
  learned, so it sees what the comparison hides. `has(key)` takes a dotted path and breaks on a
  missing, null or empty value. Each rule needs a docstring: its first line is what `explain`
  and `search` show. State one only where the app holds it for every entry. A list that breaks
  it fails the step, naming the endpoint, the path (`assets[]`) and the entry, unless a
  `Defect(..., breaks=<rule>)` covers it.

### Twins and `ignores=`

The run also sends twins: two valid values that differ along one dimension of the wire type.
A date-time varies in `time of day` and `offset`, text in `surrounding spaces` and `case`, a
`Num` in `trailing zeros`, a `List` in `order` and `duplicate` (not for ids). Other shapes have
none. A pair is sent only where the model predicts the same outcome for both. If the app answers
them apart, in the answer or the watch list, the run reports `underspecified` and exits 1. It
asks the story: the intent ignores that dimension and the app is wrong, or the book must model
it. Model it, or declare the field indifferent:
`Field(Str(format="date-time"), ignores=("time of day",), why="the product keeps one day")`.

A pair is judged on the two answers and on the rows the call made, changed or removed. A record
the world minted apart from the call is no split. A field outside your story's calls is the
product owner's to answer. `ostler book run --register-outside <calls>` adds such a finding to
`services/<name>/UNDERSPECIFIED.md` and reports it `KNOWN`. Never edit an entry or declare
`ignores=` for a field outside your story. An entry that no longer splits fails the run until
the owner's answer removes it.

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

## A backstage that reaches into the copy

A backstage that runs SQL or a one-shot service runs it through its environment, in the
play's own process: `self.environment.exec(service, argv, stdin=...)` runs a command in a
running service of the copy, and `self.environment.compose([...])` runs `docker compose`
against it. Neither starts the `ostler` command line from a book, because each start costs a
second or more on every reset. Both return the finished process and never raise on a non-zero
exit, so the backstage reads `returncode` and `stderr`.

```python
def sql(self, statement: str) -> str:
    done = self.environment.exec("api-db", ["psql", "-U", "app", "-t", "-A"], stdin=statement)
    if done.returncode:
        raise CannotArrange(done.stderr)
    return done.stdout
```

## Contracts

A contract file lists many calls, so naming the file in one `source` does not cover it.
`ostler book missing` reads each `.proto` and each OpenAPI or Swagger document of the app and
lists every call no element declares. An `Rpc` declares its `rpc` string, and an `Endpoint`
declares its method and path, with path parameters matched by position, so `/todos/{id}` and
`/todos/{todo_id}` are one call. A call no served request runs, such as an rpc the server leaves
unimplemented, goes in `App(ignore=...)` as `path/to/file.proto::Method` for a proto and
`path/to/openapi.yaml::GET /todos/{id}` for an OpenAPI operation.

A call that streams is declared like any other, with `streams = "answer"`, `"request"` or
`"both"` on the `Rpc`. It needs no `answers`, no matrix places it, and a run never plays it:
the report says `not played` and names it.
