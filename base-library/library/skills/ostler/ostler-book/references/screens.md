# Screen books

Reached from [../SKILL.md](../SKILL.md) when the service is a web app. A screen book has the
same model, matrices and journeys as an HTTP book. Where the HTTP book declares an `Endpoint`
per call, a screen book declares a `Screen` per page and an `Interaction` per thing a user
does on it. The runtime drives a headless Chromium through Playwright, which comes with the
`qa` extra of ostler; `playwright install chromium` fetches the browser once.

## A screen

One `Screen` subclass per page, form or dialog, one file each under `screens/`. Its
components are class attributes. A component is found as a user finds it, by role and
accessible name, so the app needs no test ids. Declare `None` for the id and give the label in
every language the app speaks.

```python
from ostler.book import Screen, T, request
from ostler.book.screen import Button, Field, Select, Text

class AddForm(Screen):
    api = "/todos"
    sends = (request("POST", "/todos"),)
    root = Text("add-form", does="the form element")
    title = Field(None, T("Title", "Titre"))
    save = Button(None, T("Save", "Enregistrer"))
```

| Factory | Found as |
| --- | --- |
| `Field`, `TextArea`, `DateField` | role `textbox` named by the label |
| `Select` | role `combobox`, with its options as `T` labels |
| `Button`, `Check`, `Heading`, `MenuItem`, `Link`, `Option` | the role of the same name |
| `Banner`, `Spinner` | role `alert`, `progressbar` |
| `Text` | by its text, or by `data-testid` when it has an id |

Import the factories from `ostler.book.screen`: `Field` and `Select` there are not the HTTP
names `ostler.book` exports. A component with neither id nor label is a `BookError` where it
is declared. A component with an id is found by `data-testid`; use it only where the app has
no accessible name to offer, such as a row's cells. `root` scopes every component of the
screen to one element, so two forms with a `Save` do not collide. `per_row=True` marks a
component that repeats in each row of a list.

A screen also declares what the page does: `stored` values, `phases` (what is shown, hidden
or disabled, and why) and `transitions` between them. `describe()` prints all of it in both
languages, and `check` builds it.

## An interaction

One `Interaction` per act, naming its screen, the action it carries on the model and a line on
how the surface performs it.

```python
class AddTodo(Interaction[Todo]):
    screen = AddForm
    does = "fills the add form and presses Save"
    carries = Add
```

A change that reaches the app from outside its screens, such as the clock moving or the
network dropping, is an interaction with no `screen`. The fixture it takes is what the user
types or picks, never the record: the app mints the id and the surface learns it.

## A journey

A journey is the same class as in an HTTP book, and its steps are interactions. `lang = "fr"`
opens the app in French for that journey. A `Check` step runs a probe the surface offers for
what no row shows: a button disabled while saving, a label in the wrong language.

## The surface

Subclass `PageSurface` and write only what is the app's own. It gives the book `start`,
`stop`, `set_lang`, `reset`, `strays`, `wrong_labels` and `disabled`. The book writes:

- `restore()`: put the app behind the page back to its first state, through its test hooks.
- `open()`: open the first screen and wait until it shows what it fetched.
- `perform(step)`: one branch per interaction, returning `Done(rows)` or a `Refusal`.
- `rows()`: read the list the page shows into the model's row type.

Everything else goes through `self.browser`:

| Call | Does |
| --- | --- |
| `fill(component, value, within)` | types, or picks in a select; `CannotReach` when the select does not offer it |
| `press`, `text`, `value`, `offered`, `disabled`, `visible` | click, read, read an input, list a select's options |
| `wait_for(component, state, within)` | waits for `visible`, `hidden`, `attached` or `detached` |
| `locate(component, row)`, `in_row(row, component)` | the component, or the one in the row that holds the text |
| `answered(*matchers)` | runs the body, then waits for the first answer one of them matches |
| `sent`, `holding` | waits for a request to leave, or keeps it from reaching the server |
| `set_offline(bool)` | the browser loses or regains the network |

Match requests with `request(method, path, **query)`, `answer(...)` and `refusal(...)`.

A surface waits on events, never on time: a request leaving, an answer arriving, a component
appearing, the rows an answer carries showing on screen. A book has no sleep, timer or timeout.
Wrap each act in `answered`, then wait for the page to show what the answer holds.

A surface keeps, for each record it saved, what the row shows now, so a later edit or remove
finds the row by the id the app gave it and not by its text, which two rows may share.

## How the run judges a screen

Each step runs on the model and in the page, and the rows the page then shows are compared
with the model's. A refusal is the message the page shows, so the model's rule carries the
app's words. After each step the runtime fails the step if the page sent a request under `api`
that no screen's `sends` declares. `check` builds every screen in each language and every
interaction. `run` plays the journeys, then the lifecycle cells.

A web run records a video of each journey and each cell arrangement under `<out>/videos`. It keeps
the video of one with a failed or known step, or all of them with `--keep-videos`, and the run
lists each failed or known step with the video path and the offset to seek to.

Twins and input classes read endpoint shapes, and a screen's components carry none. A screen
book reports `inputs: 0 played` and `twins: 0 pairs played`.
