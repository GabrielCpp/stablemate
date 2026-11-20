"""What a user does on the screens, and what changes around the app while they
look at it. Each interaction names its screen and the action it carries on the
model; an instance is one act, aimed at the fixture the user fills in."""

from __future__ import annotations

from ostler.book import Interaction

from .fixtures import Clock, Network, Query, Switch, Todo
from .model.actions import Add, Edit, Find, MoveClock, Remove, SwitchNetwork, SwitchStore
from .screens import AddForm, EditForm, ListPage, RemoveDialog


class AddTodo(Interaction[Todo]):
    source = ("web/app.js",)
    screen = AddForm
    does = "fills the add form and presses Save"
    carries = Add


class EditTodo(Interaction[Todo]):
    source = ("web/app.js",)
    screen = EditForm
    leads_to = ListPage
    does = "opens the row's edit form, changes what differs and presses Save"
    carries = Edit


class RemoveTodo(Interaction[Todo]):
    source = ("web/app.js",)
    screen = RemoveDialog
    leads_to = ListPage
    does = "presses Remove on the row and confirms"
    carries = Remove


class Filter(Interaction[Query]):
    source = ("web/app.js",)
    screen = ListPage
    does = "types and picks the filters above the list, reads it, then clears them"
    carries = Find


class DayPasses(Interaction[Clock]):
    source = ("web/app.js",)
    does = "the clock moves and the list is opened again"
    carries = MoveClock


class SetStore(Interaction[Switch]):
    source = ("app.py",)
    does = "the store behind the API goes down or comes back"
    carries = SwitchStore


class SetNetwork(Interaction[Network]):
    source = ("web/app.js",)
    does = "the browser loses or regains the network"
    carries = SwitchNetwork


ALL = (AddTodo, EditTodo, RemoveTodo, Filter, DayPasses, SetStore, SetNetwork)

__all__ = ["ALL", "AddTodo", "DayPasses", "EditTodo", "Filter", "RemoveTodo", "SetNetwork", "SetStore"]
