"""The home page. A server load hands it the users, and a form action adds a todo."""

from ostler.book import Field as Wire, Screen, Str, T
from ostler.book.screen import Button, Field, Link, Select, Text

from ...web.screens.labels import TITLE
from .labels import ADD, OWNER, TO_ASSIGN
from .lists import HANDED


class Home(Screen):
    source = ("kit/src/routes/+page.svelte", "kit/src/routes/+page.server.js")
    route = "/"
    name = T(en="Todos", fr="Tâches")
    first = True
    form = Text("add-form", does="the form element, posted to the add action of the page")
    title = Field("title", TITLE, "the todo's title", takes="title", holds=Wire(Str(max_len=120)))
    owner = Select("owner", OWNER, "who the todo is for", lists=HANDED)
    add = Button("add", ADD, "posts the form to the add action of the page and clears it when it lands")
    to_assign = Link("to-assign", TO_ASSIGN, "goes to the assign page without leaving the app")
    error = Text("error", does="the API's error text when the add is refused")
