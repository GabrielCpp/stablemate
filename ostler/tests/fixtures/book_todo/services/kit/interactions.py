"""What a user does in the kit app: add a todo and pick its owner, follow the links between its two pages, type the
assign page's address, and pick an assignee."""

from __future__ import annotations

from ostler.book import Interaction

from .fixtures import Todo, Who
from .model import Add, Choose
from .screens import Assign, Home


class AddTodo(Interaction[Todo]):
    source = ("kit/src/routes/+page.svelte", "kit/src/routes/+page.server.js")
    screen = Home
    does = "types the title, picks the owner and presses Add"
    carries = Add


class GoToAssign(Interaction[None]):
    source = ("kit/src/routes/+page.svelte",)
    screen = Home
    does = "follows the Assign link"


class GoBack(Interaction[None]):
    source = ("kit/src/routes/assign/+page.svelte",)
    screen = Assign
    does = "follows the Back link"


class OpenAssign(Interaction[None]):
    source = ("kit/src/routes/assign/+page.svelte",)
    screen = Assign
    does = "types the address of the assign page and loads it afresh"


class PickAssignee(Interaction[Who]):
    source = ("kit/src/routes/assign/+page.svelte",)
    screen = Assign
    does = "picks a name in the assignee list"
    carries = Choose


ALL = (AddTodo, GoToAssign, GoBack, OpenAssign, PickAssignee)
