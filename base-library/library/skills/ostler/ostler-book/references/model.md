# The model: records, state, rules, actions, cast

Reached from step 2 and step 3 of adding a route in [../SKILL.md](../SKILL.md).

## Records

A record is a frozen dataclass in `model/records.py` holding what the service keeps, not what
a caller sends. It always has its id. A state a reader can tell apart is a value on the
record (`archived: bool`) or one read off it (`status(today)`), never a stored flag the app
does not expose. A value the app derives is computed on the record, not stored.

The `Unique` key is the model's identity for the record. When the id the API shows is not
that identity, such as a row the API names by a composite of its parent and a reference, the
record keeps both: a `key` field the collection is unique on, and the id as the API shows it.

A record the book only needs to recognise, such as an address a caller types, can be an
empty class: it exists so `Id(Address)` has a kind.

## State

`model/state.py` holds one `State` subclass. Each collection is declared once:

```python
class TodoApp(State):
    todos = Collection(TodoRecord, Unique("id"), Index("assignee"))
```

A collection needs exactly one `Unique` and keeps creation order. A mode of the whole app is
a subclass with its own `rules`, such as `Serving` and `StoreDown`. A mode is a state, never a
flag on the state: "store down" is `StoreDown`, and every call that reaches the store is
refused there by a rule on that subclass. The state's rules run before the action's.

## Rules

One `Rule` per refusal, in `model/rules.py`:

```python
not_found = Rule[Todo, TodoApp]("Not found", lambda a, s, by: a.id not in s.todos, 404)
due_not_in_the_past = Rule[Todo, TodoApp]("Due date cannot be in the past", _due_moved_into_the_past,
                                         why="A chore due yesterday would show as overdue the moment it is written...")
```

- The message is the app's, word for word.
- A message that repeats what the caller sent names the request's field in braces,
  `"user {sub} not found"`. The runtime fills it from the call.
- The predicate reads the request `a`, the state `s` and the caller `by` (`None` for no
  credential). It returns True when the rule is broken.
- The status defaults to 400.
- `why` is the product's reason, in the product's words. A rule whose reason is not obvious
  from its message carries one. It is where a decision lives; there are no decision files.

## Actions

One `Action` per thing a call does, in `model/actions.py`:

```python
class AddTodo(StoreAction[Todo]):
    accept = Todo
    rules = rules.FIELD_RULES

    @staticmethod
    def reduce(a: Todo, s: TodoApp, by: Actor | None) -> Transaction:
        a.set(id=str(uuid4()))
        return Transaction(Create(s.todos, record(a)))
```

- `accept` is the fixture class the call carries. `rules` are checked in the order the app
  checks them, and the first broken one answers.
- `reduce` never mutates. A write returns a `Transaction` of primitives: `Create(collection,
  entity)`, `Update(collection, key, entity)`, `Delete(collection, key)`, `Become(StateClass)`,
  `MoveToday(date)`. A read returns `Select(collection, where=..., order=...)` or
  `Show(value)`. A grouped read returns `Total(key, value)` items.
- A create sets the fixture's id with a fresh uuid in the model. The runtime pairs it with the
  id the app answered, so the model id never has to match the app's.
- Several endpoints may carry one action when they do the same thing to the state.
- When the target and the body are different things, the action accepts an `On` subclass
  (`target`, `body`). When the action reads request headers, it accepts a `Heard`.

## Known app defects

When the app gets a call wrong and the book keeps the intended behaviour, the action lists a
`Defect`:

```python
defects = (Defect[Handover, Serving]("An unexpected error occurred", lambda a, s, by: ..., 500,
                                     why="the service copies into an account it never looks up"),)
```

The status is whatever the app wrongly answers, 204 as much as 500. The runtime expects the
defect's answer when the predicate holds and reports it as KNOWN, not FAIL. A defect also gets
its `DISAGREEMENTS.md` entry.

When the intent is a refusal, the rule stays and the defect names it with `over=`. The model
keeps refusing, and the run expects the app's wrong answer instead:

```python
defects = (Defect[Sending, Serving](rules.DELIVERY_REFUSED, lambda a, s, by: True, 503, over=rules.delivery_refused,
                                    why="a refused delivery answers 503 where 424 is meant"),)
```

A status under 400 is a success the app should not give, and the message is then the defect's
name only. When the wrong answer also changes state, `does=` returns that change the way a
`reduce` does, so later steps compare against what the app holds. `does=lambda a, s, by:
SendCommandOrders.reduce(a, s, by)` says the app marked the orders sent anyway. In a class
body, list `defects` before `rules`, since `rules` there names the action's own tuple once it is
assigned. When the app is fixed, the run fails with "the defect no longer shows, delete its
declaration".

## The cast

`model/cast.py` lists the actors a step can name with `by=`. An actor is an `Actor` subclass
carrying what the domain knows of a person: roles, a plan limit. Every actor is a standing
account that the surface signs in once, and every cell shares it.

```python
SUPPLIER = Member("supplier", (SUPPLIER_ROLE,), order_limit=3,
                  fresh="the order quota counts every billable order the account ever accepted")
```

Add an actor for a role the cast lacks only when the backstage can make its account in
every environment the book runs in. A role no environment provisions is declared `Unseen`
with `Because.NO_ACCOUNT`, as [findings.md](findings.md) says.

A record someone owns says which field names the owner: `owned_by: ClassVar[str] = "owner"`.
An actor's `identity` is what that field holds for it, the handle by default; a book whose
records hold a user id overrides it. Every id of an owned kind in a call is then also sent as
a record another actor owns, and the model's ownership rules judge it.

`fresh=` is the exception, and it carries its reason. Give it to an actor only when an
outcome you model counts what the account did in every earlier cell. A role that only gates
access is never a reason.
