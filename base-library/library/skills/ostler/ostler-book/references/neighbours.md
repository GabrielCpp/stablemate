# A record another service owns

A service that calls another service stores none of that service's records. Its book states
what its own code decides about them and takes the rest from the owner's book, by name. The
owner is the service that stores the record. Its book is the only one that holds the
record's states, its rules and the calls that move it.

Read no source outside this service. A fact about the owner comes from its book:
`ostler book search <term> --service services.<owner>` and
`ostler book explain services.<owner> <Class>`.

## What this book never holds

No record, no lifecycle matrix, no rule and no action for a record the service does not
store. A model with a `Ticket` collection in the book of a gateway is the mistake: the
ticket service's book already says what a ticket is. A service that stores nothing has a
model with no state and no action.

## The reference

```python
from ostler.book import Foreign

from ..api.model.todo import TodoRecord

TODO = Foreign(TodoRecord, owner="services.api", reads=("id", "title", "status"))
```

`owner` is the module of the owner's book. `reads` lists the fields of the owner's answers
this service reads, and no more. `check` fails a field no answer of the owner has.

## A situation that starts from the owner's state

```python
class AnOverdueTodoIsInTheDigest(Journey):
    chore = Needs(TODO, "overdue")
    given = (chore,)

    def steps(self, today):
        yield ReadDigest()
        yield ReadDigestEntry(self.chore)
```

`Needs` names a scene of the owner's lifecycle. The run asks the owner's book to reach it on
a fresh record and hands this journey the id the owner's app issued. Never perform the
owner's calls here to reach a state: how a todo becomes overdue is the owner's to change.

`Needs(TODO, "overdue", ANA)` also names the owner's cast member the record belongs to. The owner's
scene is the one in which that person takes part, and the owner's surface offers that person's account
with `account(actor)`, for a screen book to sign in with. See
[screens.md](screens.md#a-record-a-backends-book-stores).

The run reaches the owner through the owner's own surface. So this book's environment lists
the owner's hosts and secrets beside its own, under the names the owner's book gives them,
and the run says which one is missing.

## What the service does with the owner's answer

An endpoint that forwards carries no action. It states the owner's call it arrives at:

```python
def one_entry(read):
    """the todo the owner reads, under its id and its title as a label, late when it is overdue"""
    return {"id": read["id"], "label": read["title"], "late": read["status"] == "overdue"}

AS_IS = {401: 401, 404: 404}

class ReadDigestEntry(Endpoint):
    carries = None
    passes = Passes(asks=lambda step: ReadTodo(step.of), derived=one_entry, refused=AS_IS)

class FinishFromDigest(Endpoint):
    carries = None
    reaches = Reaches(lambda step: RemoveTodo(step.of), refused=AS_IS)
```

- `passes` is for a read. After the app answers, the run asks the owner the same question
  and compares the app's body with `derived` of the owner's body. `derived` says what this
  service renames, drops, filters or computes, and its docstring says so in one line.
- `reaches` is for a write. After the app answers, the run applies the owner's call to the
  owner's own model and reads the owner's app back. This book says nothing of what the call
  does.
- `refused` maps each status the owner refuses with to the status this service answers
  with. A gRPC owner's statuses are its codes by name.
- `OwnerRefused(step)` in a journey claims the owner refuses the call and the app answers as
  mapped. `Refused(step, status)` stays for a refusal this service decides on its own.

Play one situation per outcome the service's own code tells apart: passed on, refused by
the owner per status it maps, turned away by a check of its own. Do not replay the owner's
matrix through this service.

## An owner with no book yet

Name the record by a word: `Foreign("Ticket", owner="services.ticket", reads=("id",
"status"))`. `check` prints a note and passes. No journey can need that record until the
owner's book exists, and `check` fails the word once it does.

## What `check` says

It fails a read field, a needed state or a call the owner's book no longer has, in this book
and in the owner's. It fails a record this book both names foreign and holds, and a journey
that sends the owner's call directly. A `NOTE` that this book and another both hold a record
of one name is a question to settle before the book is done: either the service stores its
own record of that name, or the book is restating its neighbour and the record becomes a
`Foreign`.

## What stays an outside event

Something no service owns that happens to this one: a mail arriving, a feed, a person acting
between two commands. And a state of this service's own record that starts when another
service announces an event, in [grpc.md](grpc.md#a-state-another-service-makes).
