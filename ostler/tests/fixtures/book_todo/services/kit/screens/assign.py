"""The assign page. The browser fetches the users through the app's own gateway."""

from ostler.book import Screen, T
from ostler.book.screen import Link, Select

from ...web.screens.labels import ASSIGNEE
from .labels import BACK
from .lists import FETCHED, FETCHED_USERS


class Assign(Screen):
    source = ("kit/src/routes/assign/+page.svelte", "kit/src/routes/api/users/+server.js")
    api = "/api"
    sends = (FETCHED_USERS,)
    route = "/assign"
    name = T(en="Assign", fr="Assigner")
    reached_from = "Home: the Assign link"
    assignee = Select("assignee", ASSIGNEE, "who to assign to", lists=FETCHED)
    back = Link("to-home", BACK, "goes back to the home page without leaving the app")
