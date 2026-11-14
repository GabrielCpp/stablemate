# Screen books

Reached from [../SKILL.md](../SKILL.md) when the service is a web app. A screen book has the
same model, matrices and journeys as an HTTP book. Where the HTTP book declares an `Endpoint`
per call, a screen book declares a `Screen` per page and an `Interaction` per thing a user
does on it. The runtime drives a headless Chromium through Playwright, which comes with the
`qa` extra of ostler; `playwright install chromium` fetches the browser once.

## A screen

One `Screen` subclass per page, form or dialog, one file each under `screens/`. Its
components are class attributes. A component is found as a user finds it, by role and
accessible name, so the app needs no test ids. Declare `None` for the id. The service declares
its `languages`, and a label gives one text per declared language by name. A bare string is a
label that reads the same in every language, so an app with one language writes bare strings
and `languages=("en",)`.

```python
from ostler.book import Screen, T, request
from ostler.book.screen import Button, Field, Select, Text

class AddForm(Screen):
    api = "/todos"
    sends = (request("POST", "/todos"),)
    root = Text("add-form", does="the form element")
    name = T(en="Add a todo", fr="Ajouter une tâche")
    title = Field(None, T(en="Title", fr="Titre"))
    save = Button(None, T(en="Save", fr="Enregistrer"))
```

```python
Heading("#pane h2", "Settings")
```

| Factory | Found as |
| --- | --- |
| `Field`, `TextArea`, `DateField` | role `textbox` named by the label |
| `Select` | role `combobox`, with its options as labels |
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
or disabled, and why) and `transitions` between them. `describe(lang)` prints all of it in
one language. `check` builds it in each declared language and refuses a label that misses
one or names an undeclared one.

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
opens the app in French for that journey. With no `lang`, the journey plays in the first
language the service declares. A `Check` step runs a probe the surface offers for
what no row shows: a button disabled while saving, a label in the wrong language.

## The surface

Subclass `PageSurface` and write only what is the app's own. It gives the book `start`,
`stop`, `set_lang`, `reset`, `strays`, `wrong_labels` and `disabled`. The book writes:

- `restore()`: put the app behind the page back to its first state, through its test hooks.
- `open()`: open the first screen and wait until it shows what it fetched.
- `perform(step)`: one branch per interaction, returning `Done(rows)` or a `Refusal`.
- `rows()`: read the list the page shows into the model's row type.

A surface that needs a regional browser locale sets `locales = {"fr": "fr-CA"}` once. With no
entry the browser locale is the language name itself.

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
that no screen's `sends` declares. `check` builds every screen in each declared language and every
interaction. `run` plays the journeys, then the lifecycle cells.

A web run records a video of each journey and each cell arrangement under `<out>/videos`. It keeps
the video of one with a failed or known step, or all of them with `--keep-videos`, and the run
lists each failed or known step with the video path and the offset to seek to.

## Typed inputs

A field, text area, date field or select may declare the shape of the fixture field it takes.
The shape is the HTTP `Field`, so `ignores=` and `why=` work as on an endpoint.

```python
from ostler.book import Field as Wire, Str

due = DateField("todo-due", DUE, takes="due_on", holds=Wire(Str(format="date"), required=False))
```

`takes` and `holds` come together. The interaction on that screen then gets input classes,
and twins for each typed input. A date also gets a pair either side of the clock's midnight,
`today` and the day after. When the model reads a pair alike and the page answers it apart
(the rows it shows, or its refusal), the run reports it `underspecified`. A browser that
rejects a typed value, such as text in a date input, makes the class unreachable and not a
failure. The surface must leave the screen as it found it when `fill` raises `CannotReach`.

## A mobile app is a screen book on a device

A mobile book uses the same screens, components, interactions, typed inputs and recording as a web
book. Its surface subclasses `MobileSurface`, sets `app_id`, and `self.browser` is a `Device` on an
Android emulator or phone (`ANDROID_SERIAL` picks it). A component's `id` is the app's semantics
identifier (a Flutter `TestId`); one without an id is found by its visible text or hint.

| `Device` verb | does |
| --- | --- |
| `clear()`, `launch()`, `forward(port)` | wipe the app's data, start it, forward a device port |
| `press`, `fill`, `value`, `text`, `disabled`, `visible`, `wait_for` | as on the web |
| `heard(prefixes)`, `await_heard(prefixes, present)` | a snackbar or label by its first words |
| `await_value(component, text)` | a field comes to hold a value |

`fill` types with `adb input text`, so text outside printable ASCII is a `CannotReach`. It reads
the field back and types again, up to three times, when a keystroke was lost. The video comes from
`adb screenrecord`. The app's backstage (an auth account, a bridge that signs the device in) lives
in the book's `backstage.py`, and a surface stays short.

