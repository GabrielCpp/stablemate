"""The kit app as a surface. The runtime supplies the browser; this keeps what is the app's own: how a todo is added
and which link is followed."""

from __future__ import annotations

from typing import Any

from ostler.book import Browser, Done, Environment, Outcome, PageSurface, Refusal, action

from ..web.backend import Backend
from .fixtures import Todo
from .interactions import AddTodo, GoBack, GoToAssign, OpenAssign, PickAssignee
from .screens import ALL as SCREENS, Assign, Home


class KitWeb(PageSurface):
    name = "kit"
    host = "kit"

    def __init__(self, environment: Environment, lang: str = ""):
        super().__init__(environment, SCREENS, lang)
        self.backend = Backend(environment.address("api"))

    def drive(self, environment: Environment, lang: str) -> Any:
        return Browser(environment.address(self.host), lang, lang_query=None)

    def restore(self) -> None:
        self.backend.reset()

    def open(self) -> None:
        self.browser.open(Home.route)
        self._ready()

    def _ready(self) -> None:
        self.browser.page.wait_for_selector('[data-testid="add-form"][data-ready="true"]')

    def _listed(self) -> None:
        self.browser.page.wait_for_function(
            "() => document.querySelector('[data-testid=\"assignee\"]').options.length > 1")

    def perform(self, step: Any) -> Outcome:
        b = self.browser
        match step:
            case AddTodo():
                return self._add(step.of)
            case GoToAssign():
                b.press(Home.to_assign)
                b.page.wait_for_url("**/assign")
                self._listed()
            case GoBack():
                b.press(Assign.back)
                b.page.wait_for_url("**/")
                self._ready()
            case OpenAssign():
                b.open(Assign.route)
                self._listed()
            case PickAssignee():
                b.fill(Assign.assignee, step.of.name)
            case _:
                raise TypeError(step)
        return Done(self.rows())

    def rows(self) -> tuple[()]:
        return ()

    def _add(self, todo: Todo) -> Outcome:
        b = self.browser
        b.fill(Home.title, todo.title or "")
        b.fill(Home.owner, todo.assignee or "")
        with b.answered(action("/", "add")) as got:
            b.press(Home.add)
        if got.json()["type"] == "failure":
            b.wait_for(Home.error)
            return Refusal(b.text(Home.error), 0)
        b.page.wait_for_function("() => document.querySelector('[data-testid=\"title\"]').value === ''")
        return Done(self.rows())
