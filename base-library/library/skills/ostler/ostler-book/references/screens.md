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
    source = ("web/add_form.tsx",)
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
| `Select` | role `combobox`. A native select or a popup of options (a combobox that opens a `listbox` of `option` entries), driven the same way. A fixed list of choices goes in `options=(...)`, as labels. A list filled from data states what it holds with `lists=` |
| `Form` | role `form`, `group` or `region` by its accessible name. A form the page draws from data states its fields with `lists=`, each entry a name and a role |
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

## A list filled from data

```python
from ostler.book import request
from ostler.book.screen import Lists, Select

def by_name(users):
    """the users received, by name"""
    return sorted(u["name"] for u in users)

def owners(model, by):
    """everyone a todo the list holds is assigned to"""
    return sorted({t.assignee for t in model.todos if t.assignee})

def not_me(model, by):
    """the person looking"""
    return [by.handle]

assignee = Select("list-assignee", ASSIGNEE, "filters by owner",
                  lists=Lists(head=(ANYONE,), given=request("GET", "/users"), derived=by_name,
                              always=owners, never=not_me))
```

The run judges the list when a journey picks in it or reads it with `labels(component)`: it reads
the labels the select shows and compares them with the `head` labels followed by `derived` applied to the last answer the page
received to `given`. `derived(body, url)` may take the URL of the request answered as a second
argument, the page's URL for `handed`, and `''` for `asked`. A difference fails the step and the
note names both orders. The report names the lists a pick judged, the stated ones no pick reached and the selects nobody stated.

`always` names who must be offered and `never` who must not, each a read of the model for the
person looking, taken before the step. Entries neither names are ignored, so the claim holds
on an environment that keeps other people's records. A derivation follows the data the page
was given, and these two do not, so a list a backend fills wrongly needs them. A list may
state any of the three claims alone.

`entries=(in_order(), no_repeat())` states rules every entry holds whatever records the list
holds, so they hold on a shared environment. `in_order(key)` and `no_repeat(key)` take no key
(the entry itself), a function, or a dotted path read from a dict entry. A rule is any function
from the entries to what breaks it, with a docstring whose first line `describe`, `search` and
`explain` print. `entries` takes a tuple, not one rule. At each pick the run judges each rule
over the entries after the `head`, native select or popup alike, and a break names the list,
the rule and the entries.

Read the claims from the code that builds the list. A sort (`sort`, `toSorted`, `orderBy`, an
`ORDER BY` the app's own endpoint runs) is `in_order(key)`, with the key the sort reads. A dedup
(a `Set`, `uniqBy`, a `filter` that keeps the first index of a value) is `no_repeat(key)`. A default
selection, an initial value bound to the control or an option marked `selected`, is `picked`.

`picked=ANYONE` states the entry the list has selected before a person picks, as a label or a
function of the model and the person looking, with a docstring. The run judges it on the first
pick in that list after the page loads, reading the selected option (in a popup, the option
marked `aria-selected`, else the button's own text). A list of an edit form that starts on the
record's own value states no `picked`. The report adds, per read list, the claims a pick judged.

`check` notes, and does not fail on, each select that states a shape and says nothing about its
list. A select with no shape and no claim stays a finding that blocks the run.

A SvelteKit app renders some lists from data its server loaded and fetches others in the browser
through its own endpoints. Tell them apart in the source. A list filled from the `data` of a
`+page.server.js` or `+page.server.ts` load (or a `+layout.server` one) is `given=handed(route)`,
the route spelled as its folders spell it, `/tickets/[id]` for `src/routes/tickets/[id]`. A list
filled by a `fetch` in a `.svelte` file, or by a call to the app's own `/api` routes
(`+server.js`), is `given=request(method, path)`. A `+page.js` or `+page.ts` universal load is not
handed: the server answers `__data.json` for server loads only and skips a node that has none, so
name the `fetch` the universal load makes with `request`. A step that submits a form action of the
page (`export const actions`, a `<form method="POST">`) waits on `action(route, name)`. `derived`
takes the data the page was handed, a dictionary as the page's `data` prop sees it.

```python
from ostler.book import handed

def handed_by_name(data):
    """the users the page was handed, by name"""
    return sorted(u["name"] for u in data["users"])

owner = Select("owner", OWNER, "who the todo is for", lists=Lists(given=handed("/"), derived=handed_by_name))
```

At the pick the run asks the app's server for `<path>/__data.json` again, in the browser's own
session, decodes it and compares as above. A page whose path is not on the route fails the pick
and the note names both. A list the browser fetches through the app's gateway keeps
`given=request(...)`.

A list can also be asked of a backend through its book: `given=asked(ListTodos)` names an endpoint
class of another book under the root. Before each step on the screen the run sends that call as the
person taking the step, through the owner's surface, and derives the list from the answer exactly
as from a received one. A call built with no input must be enough. An owner with no book, a refusal
or a call that cannot be built is a fault on the list that names the call and why. `asked` works
on the web too, and on a phone it is the fallback where the app cannot be pointed at a port ostler
holds. A phone book that runs the app against a fixed host port declares `listens` (below), and its
lists read the app's own request with `request(...)`. A list on a phone screen without `listens`
states `given=asked(<Endpoint>)`: find the call the app's client code makes to fill the list (the
repository or API client the screen's state reads), then take the `Endpoint` of the backend's book
that declares that route. Find it with `ostler book search <path>` over the root. A backend that
answers a moment after the page got its data gives the same data only for a list that changes
slowly (A6): a busy shared list keeps `always`, `never` and `entries`.

## A form drawn from data

A form the page draws from data is a list whose entries are its fields. Each entry is a pair of
the field's accessible name and its ARIA role, and the role is the field's kind: `textbox`,
`spinbutton`, `combobox`, `checkbox`, `radiogroup`, `switch`, `slider` or `listbox`.

```python
from ostler.book import Form, T, no_repeat, request
from ostler.book.screen import Lists

ROLE = {"text": "textbox", "number": "spinbutton", "choice": "combobox", "flag": "checkbox"}

def definition_fields(answer):
    """each field of the details form, with its label and kind, in the definition's order"""
    return [(field["label"], ROLE[field["type"]]) for field in answer["fields"]]

fields = Lists(given=request("GET", "/definition"), derived=definition_fields, entries=(no_repeat(),))
details = Form("details-form", T(en="Details", fr="Détails"), "the fields drawn from the definition", lists=fields)
```

`Form(id, label, does, lists=Lists(given=..., derived=...))` is found by role `form`, `group` or
`region` with its accessible name, or by its id. A form with no accessible name is found, with no id,
by the heading it holds or by the name of its submit button, and a form with an id and no accessible
name is a finding of the label check: give it `aria-label` or `aria-labelledby`. `derived` returns the pairs in the order the page
draws them. Read the role of each pair from the code that renders each field kind.

A step reads the form with `browser.fields(Screen.form)` when a journey shows it. A difference
fails the step, and the note names both sequences. A control with no accessible name is a fault of
its own. `entries` rules judge the names, and `of_pairs(rule)` hands a rule the pairs of name and
role instead. `always` and `never` judge the names. The report lists a `Form` like a
select.

## An interaction

One `Interaction` per act, naming its screen, the action it carries on the model and a line on
how the surface performs it.

```python
class AddTodo(Interaction[Todo]):
    screen = AddForm
    source = ("web/add_form.tsx",)
    does = "fills the add form and presses Save"
    carries = Add
```

An interaction that belongs to no screen names no source.

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
| `fill(component, value, within)` | types, or picks in a select, native or a popup; `CannotReach` when the select does not offer it |
| `press`, `text`, `value`, `offered`, `disabled`, `visible` | click, read, read an input, list a select's options (`offered` works on a native select and on a popup) |
| `wait_for(component, state, within)` | waits for `visible`, `hidden`, `attached` or `detached` |
| `locate(component, row)`, `in_row(row, component)` | the component, or the one in the row that holds the text |
| `answered(*matchers)` | runs the body, then waits for the first answer one of them matches |
| `sent`, `holding` | waits for a request to leave, or keeps it from reaching the server |
| `set_offline(bool)` | the browser loses or regains the network |

Match requests with `request(method, path, **query)`, `answer(...)` and `refusal(...)`. A `{id}` in
the path stands for one segment, as in `request("PATCH", "/projects/{id}/variants")`. A form
action of a SvelteKit page is `action(route, name)`, which matches the answer to `POST /?/add` for
`action("/", "add")`, to wait on with `answered`.

A surface waits on events, never on time: a request leaving, an answer arriving, a component
appearing, the rows an answer carries showing on screen. A book has no sleep, timer or timeout.
Wrap each act in `answered`, then wait for the page to show what the answer holds.

A surface keeps, for each record it saved, what the row shows now, so a later edit or remove
finds the row by the id the app gave it and not by its text, which two rows may share.

## How the run judges a screen

Each step runs on the model and in the page, and the rows the page then shows are compared
with the model's. A refusal is the message the page shows, so the model's rule carries the
app's words. After each step the runtime fails the step if the page sent a request under `api`
that no screen's `sends` declares. With `api = "/api"` that judges the app's gateway endpoints. The data
handed with a page and the form actions are not under it, so they are never strays. `check` builds every screen in each declared language and every
interaction. `run` plays the journeys, then the lifecycle cells.

A web run records a video of each journey and each cell arrangement under `<out>/videos`. It keeps
the video of one with a failed or known step, or all of them with `--keep-videos`, and the run
lists each failed or known step with the video path and the offset to seek to.

## Typed inputs

A field, text area or date field a person fills declares the shape of the fixture field it takes,
and the check names one that does not. A select states its options, what its list holds, or a
shape. The shape is the HTTP `Field`, so `ignores=` and `why=` work as on an endpoint.

```python
from ostler.book import Field as Wire, Int, Str

title = Field("todo-title", TITLE, takes="title", holds=Wire(Str(max_len=120)))
quantity = Field("todo-quantity", QUANTITY, takes="quantity", holds=Wire(Int(), required=False))
due = DateField("todo-due", DUE, takes="due_on", holds=Wire(Str(format="date"), required=False))
```

A required text is also tried blank, and a number is also tried with text.
`takes` and `holds` come together. The interaction on that screen then gets input classes,
and twins for each typed input. A date also gets a pair either side of the clock's midnight,
`today` and the day after. When the model reads a pair alike and the page answers it apart
(the rows it shows, or its refusal), the run reports it `underspecified`. A browser that
rejects a typed value, such as text in a date input, makes the class unreachable and not a
failure. The surface must leave the screen as it found it when `fill` raises `CannotReach`.
A select is weighed on what it offers, so it gets no twins of spelling, such as case or spaces.
[inputs.md](inputs.md) lists the classes and twins each shape gets.

A stated shape is tried only through an interaction of that screen whose fixture has the field,
and the check names a stated field that no interaction fills. The run's `fields:` line says how
many stated fields it tried.

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

`fill` on a `select` opens the list with a tap and reads the entries that appeared: the texts on the
screen after the tap that were not on it before, top to bottom then left to right. The choice before
the tap is the select's own text. A phone judges `derived` (from `request(...)` through a `listens` proxy, or from `asked`), `always`, `never`,
`entries` and `picked` as the web does, then taps the entry whose text is the value. A value the list
does not show closes it with Android back and is a `CannotReach` that names what it offers. A phone
with no `listens` sees no request, so a list whose `given` is `request(...)` or `handed(...)` is a fault
saying so, and `handed(...)` is that fault on a phone with `listens` too.

`listens = {19080: "api"}` on the `MobileSurface` maps a host port the app sends its requests to onto
the environment host those requests are for. While the surface runs, ostler holds a recording reverse
proxy on that port, forwarding to the copy's address of the host, so a plain HTTP target needs no
certificate and the app needs no change. After a step starts, a list stated `request("GET", "/v1/items")`
is judged from the first matching exchange the app sent through the proxy since the step began, else
the last one before it, its body and URL. A port already held fails the start and names the holder. An app that reaches the
backend through a bridge on that port (a `socat` step) leaves the port to ostler: drop the bridge.
`labels(component)` opens a list, judges it as a pick does, and closes it. `picked` is judged again after `launch()`
or `clear()`.

`fill` types with `adb input text`, so text outside printable ASCII is a `CannotReach`. It reads
the field back and types again, up to three times, when a keystroke was lost. The video comes from
`adb screenrecord`. The app's backstage (an auth account, a bridge that signs the device in) lives
in the book's `backstage.py`, and a surface stays short.

