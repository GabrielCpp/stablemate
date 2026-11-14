"""The only route. Shows the list, holds the add form above it, and turns one
row into the edit form or opens the remove dialog."""

from ostler.book import Phase, Screen, Stored, T, Transition, When, request
from ostler.book.screen import Banner, Button, Select, Spinner, Text

from .labels import ANYONE, ASSIGNEE, STATUS, STATUSES

search = Text("list-search", T(en="Search", fr="Rechercher"), "filters by title or description as you type")
assignee = Select("list-assignee", ASSIGNEE, (ANYONE, "ana", "bo"), "filters by owner")
status = Select("list-status", STATUS, (T(en="Any", fr="Tous"),) + STATUSES, "filters by derived status")
loading = Spinner("list-loading", "the first fetch is out")
empty = Text("list-empty", T(en="Nothing to do", fr="Rien à faire"), "the fetch returned no row")
rows = Text("todo-list", does="one row per todo, in the API's order")
row_title = Text("row-title", per_row=True)
row_assignee = Text("row-assignee", per_row=True)
row_due = Text("row-due", per_row=True)
row_status = Text("row-status", per_row=True, does="one of the three status labels")
edit = Button("row-edit", T(en="Edit", fr="Modifier"), "replaces this row with the edit form", per_row=True)
remove = Button("row-remove", T(en="Remove", fr="Supprimer"), "opens the remove dialog for this row", per_row=True)
offline = Banner("offline-banner", T(en="You're offline", fr="Vous êtes hors ligne"), "navigator.onLine is false")

loading_phase = Phase("loading", shows=(loading,), hides=(rows, empty))
empty_phase = Phase("empty", shows=(empty,), hides=(loading, rows))
ready = Phase("ready", shows=(rows,), hides=(loading, empty))
offline_phase = Phase("offline", shows=(offline, rows), disabled=(remove,),
                      because="a write cannot reach the API; the rows are the last fetch")


class ListPage(Screen):
    source = ("web/index.html", "web/app.js")
    api = "/todos"
    sends = (request("GET", "/todos"),)
    route = "/"
    name = T(en="Todos", fr="Tâches")
    first = True
    title = Text("list-title", T(en="Todos", fr="Tâches"))
    search = search
    assignee = assignee
    status = status
    loading = loading
    empty = empty
    rows = rows
    row_title = row_title
    row_assignee = row_assignee
    row_due = row_due
    row_status = row_status
    edit = edit
    remove = remove
    offline = offline

    stored = (
        Stored("rows", "the todos of the last successful fetch, as the API sent them", "[]"),
        Stored("loaded", "whether any fetch has answered", "false"),
        Stored("filters", "text, assignee, status as typed and chosen", "all empty"),
        Stored("editingId", "the id of the row shown as the edit form, or null", "null"),
        Stored("removingId", "the id the remove dialog asks about, or null", "null"),
        Stored("online", "navigator.onLine, kept current by the online/offline events", "navigator.onLine"),
    )
    phases = (loading_phase, empty_phase, ready, offline_phase)
    transitions = (
        Transition(loading_phase, When("200 with rows"), ready, then="rows replaced"),
        Transition(loading_phase, When("200 with no row"), empty_phase),
        Transition(ready, When("change", search), ready, then="refetch within 200 ms"),
        Transition(ready, When("change", assignee), ready, then="refetch"),
        Transition(ready, When("change", status), ready, then="refetch"),
        Transition(ready, When("a write answered 2xx"), ready, then="refetch"),
        Transition(ready, When("60 s pass"), ready, then="refetch"),
        Transition(ready, When("click", edit), ready, then="editingId = row id; the row is the edit form"),
        Transition(ready, When("click", remove), ready, then="removingId = row id; the dialog opens"),
        Transition(ready, When("offline event"), offline_phase, then="no refetch until online"),
        Transition(offline_phase, When("online event"), ready, then="refetch"),
    )
