# A gRPC service

Reached from [../SKILL.md](../SKILL.md) when the service answers gRPC calls. Everything in
the skill holds. This page says what changes: how a call is declared, what an answer looks
like, and what the services of one repo share.

The runtime sends each call through `grpcurl`, which reads the service's own description by
reflection. `grpcurl` must be on `PATH` and the service must serve reflection. A book needs no
generated code.

## A call

One `Rpc` class per unary call, in `endpoints/`. It is an `Endpoint` with no method, path,
params or query: the request message is the `body`, and a call with an empty request
declares no body.

```python
class GetUser(Rpc):
    rpc = "user.v1.UserService/GetUser"
    host = "user"
    auth = (Bearer(),)
    body = GET_USER
    answers = (
        Answer(Code.OK, USER, "the user, with the email and the phone the caller may see"),
        Answer(Code.NOT_FOUND, STATUS, "nobody goes by this handle or email"),
        Answer(Code.INVALID_ARGUMENT, STATUS, "no sub was sent"),
        NOT_SIGNED_IN,
    )
    source = (SERVICE + "Get", SERVICE + "lookup")
    does = "Reads one user. Staff see anyone's email; a phone is shown to its owner only."
    carries = actions.ReadUser
```

- `rpc` is `package.Service/Method`, as the proto file names it.
- `host` names the entry of the environment's `hosts` the call goes to, one per service.
- A status is a `Code` by name: `Code.OK`, `Code.NOT_FOUND`, `Code.FAILED_PRECONDITION`.
  Never a number. A `Rule`, a `Defect` and a `Refusal` take the same `Code`.
- Every answer that is not `Code.OK` has the shape `STATUS`, which is the message the service
  gave. A call that accepts a credential declares `Code.UNAUTHENTICATED`.
- A call: `GetUser(Lookup("casey"), by=ALEX)`. The fixture is the request message.
- A call whose answer is an empty message declares no shape: `Answer(Code.OK, None, "the policy is gone")`.

## The request message

The fixture is a dataclass with one field per field of the request message, under the proto
name.

- **A nested message is a nested fixture.** `UpsertPolicyRequest { Policy policy }` is
  `Upsert(policy: Terms)`, where `Terms` is a dataclass with the fields of `Policy`. The
  runtime packs it by the shape the body declares.
- **A field whose name is a Python keyword takes an underscore**: `from` is written `from_`
  in the fixture and in a record class of the model, and `**{"from": Field(...)}` in the
  `Object`. The wire and the report say `from`.
- **A field the caller may leave out is `required=False`**, with what leaving it out means in
  `does=`. The service reads a field left out as its zero value, so "left out" and "sent
  empty" are one case.
- **A fixture that writes gives `examples(cls, state, by)`.** `explore` cannot derive a
  request with a nested message or a pair of fields that must agree, and `check` says so.

## What an answer looks like

- **A field is named as the proto file names it**, `team_id`, in a request, in an answer and
  in a fixture. The JSON spelling `teamId` appears nowhere in a book.
- **A scalar is always there.** The service sends a zero value as `""`, `0` or `false`, and
  the answer carries it. A field the service withholds reads as its zero value, so the model
  says `""`, never `None`, and the field is not `nullable`.
- **A message or a timestamp nobody set reads as null.** Declare it `nullable=True`.
- **An enum reads as its name**, `USER_ROLE_AGENT`. **A timestamp** is `Str(format="date-time")`.
  **A 64-bit integer** is `Int()`.
- **A list nobody filled reads as `[]`.**

## Input classes

The wire is typed, so a wrong type or a value outside an enum never reaches the service, and
the runtime plays neither. A null is a field left out, so it plays no null either. It plays
what a typed caller can still send: a blank, a required field left out (which the service
reads as the zero value), a value past a bound. The service-wide `Refusals(missing=...)`
names what a missing required field earns when one message covers the service; a call that
says something else overrides `refusals`.

An id that filters a list, such as the team of `ListAtRisk`, names nothing and still answers
OK with an empty list. The runtime plays an unknown id and another record's id against every
`Id` field and expects a refusal, so declare each one:

```python
diverges=tuple(Diverges(ListAtRisk, f"team_id {kind}", why="The team is a filter: a name that matches no team lists nothing.")
               for kind in ("unknown", "wrong kind")),
```

Write no `Refusals` entry for a refusal the service never gives.

## A message that quotes the request

A refusal that repeats what the caller sent names the request's field in braces. The runtime
fills it from the call.

```python
user_not_found = Rule[Lookup, Directory]("user {sub} not found",
                                         lambda a, s, by: s.found(a.sub or "") is None, Code.NOT_FOUND)
```

The name in braces is a field of the fixture the action accepts. A message that quotes
something the request did not send, such as a stored name, cannot be written this way: make
the answer's `message` opaque with the reason, and list it in the report.

## What the services of one repo share

A repo of several services keeps one package beside the service books, `services/shared/`,
and every book imports it. Read it before writing anything: what it holds is not written
again.

| Module | Holds |
| --- | --- |
| `accounts.py` | the standing accounts as actors, with the role and team each has, and `CAST` |
| `answers.py` | the answers and rules every service gives: not signed in, forbidden, the timestamp shape |
| `places.py` | the environments, one host per service, and the stack |
| `surface.py` | the surface: how each account gets its credential before a cell |

A rule or an answer a second service needs moves into `shared` then, never copied. A book
adds to `shared` only what another service's source also does.

Every call names its caller, `by=ALEX`. `by=None` sends no credential.

## A world of shared records

Some worlds have a fixed set of accounts and no tenant, and some records are keyed by a
name, such as one policy per category and priority. A cell cannot make its own copy of such
a record, so two rules replace "a cell makes what it acts on" for these records only:

- **The model starts with what the seed made.** `new_model` fills the collection with the
  seeded records, read from the app's seed source.
- **The surface puts them back before each cell.** The service's surface subclasses the
  shared one and its `restore()` reads the records through the product's own calls, as an
  account allowed to edit them, then writes back what differs among the named shared
  records. It never writes to the store and leaves every other record as it found it. Say in
  the docstring which calls it uses.

An id that is a name, such as a team id that is the team's name in lower case, is
`Id(Record, Str(), "<why it is read as written>")`.

A read the surface makes for its own use, `ListPolicies(by=ADMIN).send(self.client).body`,
comes back under proto names like every other answer.

A seeded record no call adds or removes still gets a matrix: one scene, and a column per
kind of caller and target that the service tells apart, such as read by herself, read by
staff, read by nobody. Its `state_of` answers the scene's name for every record.

## A state another service makes

A service that reacts to another one keeps states no call of its own reaches: a timer that
starts when the ticket service announces a ticket. The book makes that change itself and
reads until it has landed.

- **The change is an outside event.** One `Arrange` subclass per thing a person does at the
  other service, in `outside.py`, listed in `Service(outside=...)`. Its `carries` is an
  action of this book's model: what this service does when it hears.

  ```python
  class Opens(Arrange[Ticket]):
      does = "A customer opens a ticket. Both of its timers start."
      carries = actions.TicketOpened
  ```

- **The surface performs it by sending the other service's own call**, imported from that
  service's book, `services/ticket/endpoints`. A call that book lacks is declared there,
  never here. The call must succeed, so the surface raises `BookError` on a refusal: the
  other service's refusals belong to its own book.
- **The watch is what the run waits on.** After an outside event the runtime reads the watch
  again until it shows what the model says, up to a thousand reads, and judges the last
  reading. Write no sleep, no retry and no deadline. The surface adds a read of each record
  the cell made to `self.watch` as it makes it, sent by an account allowed to read it, and
  `restore()` sets the watch back to `self.standing`. An event whose change no watch read
  compares is not waited for, and the next step races it.
- **The model names the record.** The action that hears of a new record gives it an id,
  `a.set(ticket_id=f"ticket-{n}")`, and the surface learns the app's id for it from the other
  service's answer: `self.client.ids.learn(TicketSlaRecord, model_id, real_id)`. A refusal
  that quotes the id is compared under the model's id.
- **A cell asks only about what it made.** A list or a count over a team, a queue or a day
  holds what other cells and other people made. Give the cell's record a scope only it has,
  such as a team whose id is `minted`, and ask within it. A
  column that cannot be scoped in a scene is `Impossible("<why>")`.
- **Read only what a cell made.** Once an outside event makes the record, the model keeps no
  seeded one. A seeded record has aged since the seed: its minutes, its targets and its flags
  drift, and a field left opaque for the seeded ones is unchecked for every record. With only
  the cell's own records, a timer's target and its warned and breached flags are compared.
  The health journey makes one too, so a bus that carries nothing reads as "could not judge".
- **A scope's name is minted once.** Journeys share a model, so two tickets handed to the
  model's team `desk` are in one team: the runtime sends one generated name for `desk` for as
  long as the client lives.
- **A record that keeps acting is ended.** An open ticket's timer breaches hours later and
  pages a team. `restore()` and `stop()` end what the last cell opened, through the other
  service's own call. Say so in the docstring and list it in the report.
- **A minute count is bounded by the product's own windows.** A fresh timer has its whole
  target left, less the minutes its cell has run. Ask a list within a window well under the
  target and one well over it; the model predicts both. A window within five minutes below
  the target is not asked.

## A list answer and an unseen field

An answer message that wraps a list, `ListPoliciesResponse { repeated Policy policies }`, is
one record with a tuple field, and the action returns `Show(PolicyList(...))`.

A field or an answer the run cannot draw is declared by the code's name:
`Unseen(ListAtRisk, "OK: tickets[].sla.resolution.stopped_at", Because.NEVER_FILLED, "<why>")`,
or `"NOT_FOUND"` for a whole answer.

## A value the clock sets

The runtime cannot set the service's clock. A value that moves with it, such as the minutes
a timer has left, is `opaque=` with the reason. Before making a value opaque, look for a
request that pins it: a window given by two instants in the past, a bound wide enough to
hold every record. List every clock-driven value left opaque in the report.

List every shared record a restore puts back in the report: a run on a shared environment
changes them under whoever else is using it.

## What the format cannot express yet

Report a call that needs one of these, and leave it out of the book:

- a call that streams its answer or its request,
- status details beyond the code and the message,
- a defect whose own message quotes the request.
- a call of the book's own service whose effect lands after its answer,
- a breach, or a minute count at its exact boundary: both need a clock the book sets.
