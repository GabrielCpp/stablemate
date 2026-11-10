# Matrices, fixtures and journeys

Reached from steps 5 and 6 of adding a route in [../SKILL.md](../SKILL.md).

## The lifecycle matrix

One `Axes` per record, in `model/lifecycle.py`. Rows are scenes, the states a record can be
in, with a `(none)` row. Columns are actions, each aiming one call at the record in that
scene. The runtime computes each cell from the model: the next state and its changes, a
refusal, a no-op, or impossible.

```python
CHORE_SCENES = (
    Scene("(none)", "no todo is listed", lambda today: ()),
    Scene("scheduled", f"{CHORE!r} is listed with a due day on or after today",
          lambda today: (AddTodo(scheduled(today, 2, title=CHORE)),)),
)

CHORE_ACTIONS = {
    "add": lambda m: AddTodo(todo(CHORE)),
    "read": _on_chore(lambda m, c: ReadTodo(c)),
    "update, by a colleague": _on_chore(lambda m, c: UpdateTodo(c.set(title="Mine now"), by=COLLEAGUE)),
}

MATRICES = (
    Axes[TodoApp]("chore", TODAY, CHORE_SCENES, CHORE_ACTIONS, chore_status,
                  state_of=lambda m, t: t.status(m.today), entities=lambda m: m.todos),
)
```

- `Scene(name, when, reached_by)`. `when` says how a reader tells the scene apart.
  `reached_by(today)` returns the steps that bring the app there from nothing, using the
  standing actors. The steps create every record the scene needs.
- An action is `model -> call`. A helper such as `_on_chore` finds the record in the model
  and builds the call on `Fixture.of(record)`, or returns `Impossible("<why>")` where the pair
  cannot occur.
- `told_apart(model)` names the scene the model is in. `state_of(model, entity)` names the
  scene of one entity, and `entities(model)` lists them; both are left out where the record is
  the app itself.
- A move no caller makes, such as time passing, is a column whose name starts with `on:`.
- A cell's scope is the part of the state the matrices naming its endpoint care about, so a
  column added to the right matrix keeps the walk small. An endpoint no matrix names is
  played in every state of the app, which multiplies the replay.

## Fixtures

A fixture is what a caller sends, a `@dataclass(eq=False)` subclass of `Fixture` in
`fixtures/`. It is not the record: it has no id until the app answers.

- One base factory per fixture and variants that fill one thing in and pass the rest
  through, so a journey composes what it needs in one line:
  `scheduled(today, 2, title="Call the plumber", assignee="ana")`.
- `fixture.set(**fields)` changes the caller's picture in place: the thing moved on.
  `fixture.but(**fields)` is one attempt that leaves the fixture as it was, for a call that
  may be refused.
- `Fixture.of(record)` builds the fixture that stands for a stored record.
- A fixture for a path with a query carries the query's fields beside the path's.
- `examples(state, by)` is a classmethod a fixture overrides when `explore` cannot derive
  bodies on its own, such as a body that must name records the state holds.
- Every factory and variant is listed in `fixtures/__init__.py`'s `__all__`.

## Journeys

A journey is a story a user lives through, one class per file in `journeys/`, registered in
`journeys/__init__.py`'s `ALL`. The docstring tells the story in plain words; the steps follow
it.

```python
class AWeekOfChores(Journey):
    """Ana writes down three chores, hands one to Bo, finishes one, and looks at what is left."""

    def steps(self, today: date):
        milk = scheduled(today, 1, title="Buy milk", assignee="ana")
        yield AddTodo(milk, by=ANA)
        yield RemoveTodo(milk, by=ANA)
        yield Listed()
```

A step is an endpoint call, or a claim:

- `Listed(*fixtures)`: these rows, in this order, among what the journey made. Rows the app
  held before the journey began are taken out first. `Listed()` claims nothing the journey
  made is still listed.
- `Same(first, again)`: two calls answered the same.
- `Relates("<claim>", (a, b), fn)`: `fn(a, b)` returns None when the claim holds, or what was
  seen instead.
- `Check("<claim>", probe)`: a claim about the surface itself; `probe(surface)` returns None
  or what was seen.

`given = (Given(call, undo=call),)` arranges a mode before the steps and undoes it after.
`alone = True` makes the journey run with nothing else beside it; give it only to a journey
that changes the whole app's mode. A journey every route of the batch reaches is better than
one journey per route: it is the story a reviewer reads.
