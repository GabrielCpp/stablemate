"""The web app as a surface: the screens as a user drives them. The runtime
supplies the browser; this keeps what is the todo app's own. The surface keeps,
per todo it saved, what the row shows now, so a later edit or remove finds its
row by the id the app gave it and not by its text, which two rows may share."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator, cast

from ostler.book import CannotReach, Done, Environment, Outcome, PageSurface, Received, Refusal, answer, refusal, request

from .backend import Backend
from .fixtures import Query, Todo
from .interactions import AddTodo, DayPasses, EditTodo, Filter, RemoveTodo, SetNetwork, SetStore
from .model.rules import as_date
from .model.todo import Row
from .screens import ALL as SCREENS, AddForm, EditForm, ListPage, RemoveDialog
from .screens.labels import STATUSES

STATUS_VALUES = dict(zip(STATUSES, ("unscheduled", "scheduled", "overdue")))
ROWS = '[data-testid="todo-row"]'


def _typed(due: date | str | None) -> str | None:
    return due.isoformat() if isinstance(due, date) else (due or None)


class TodoWeb(PageSurface):
    locales = {"en": "en-US", "fr": "fr-CA"}

    def __init__(self, environment: Environment, lang: str = ""):
        super().__init__(environment, SCREENS, lang)
        self.backend = Backend(environment.address("api"))
        self._shown: dict[str, Todo] = {}
        self._app_ids: dict[str, str] = {}

    def restore(self) -> None:
        self.backend.store_down(False)
        self.backend.reset()
        self._shown.clear()
        self._app_ids.clear()

    def open(self) -> None:
        with self.browser.answered(answer("GET", "/users")) as users:
            with self._listed():
                self.browser.open(ListPage.route)
        self.browser.page.wait_for_function(
            "n => document.querySelector('[data-testid=\"list-assignee\"]').options.length === n", arg=len(users.json()) + 1)

    def today(self) -> date:
        return self.backend.today()

    def perform(self, step: Any) -> Outcome:
        match step:
            case AddTodo():
                return self._add(step.of)
            case EditTodo():
                return self._update(step.of)
            case RemoveTodo():
                return self._remove(step.of)
            case Filter():
                return self._find(step.of)
            case DayPasses():
                self.backend.set_today(as_date(step.of.today))
                self.open()
            case SetStore():
                self.backend.store_down(step.of.down)
            case SetNetwork():
                self._offline(step.of.offline)
            case _:
                raise TypeError(step)
        return Done(self.rows())

    def rows(self) -> tuple[Row, ...]:
        self.browser.wait_for(ListPage.title)
        self.browser.wait_for(ListPage.loading, "hidden")
        out = []
        for li in self.browser.page.locator(ROWS).all():
            status = self.browser.in_row(li, ListPage.row_status).inner_text()
            out.append(Row(
                self.browser.in_row(li, ListPage.row_title).inner_text(),
                self.browser.in_row(li, ListPage.row_due).inner_text() or None,
                self.browser.in_row(li, ListPage.row_assignee).inner_text() or None,
                next(v for label, v in STATUS_VALUES.items() if label[self.lang] == status),
            ))
        return tuple(out)

    def _offline(self, offline: bool) -> None:
        if offline:
            self.browser.set_offline(True)
        elif self.browser.visible(ListPage.offline):
            with self._listed():
                self.browser.set_offline(False)
        self.browser.wait_for(ListPage.offline, "visible" if offline else "hidden")

    @contextmanager
    def _listed(self, **query: str) -> Iterator[Received]:
        """Runs the body, waits for the list the app then fetches (filtered as
        `query` says) and for the screen to show every row of it."""
        with self.browser.answered(answer("GET", "/todos", **query)) as got:
            yield got
        self._shows(got)

    def _shows(self, got: Received) -> None:
        body = got.json()
        if isinstance(body, list):
            self.browser.page.wait_for_function(
                "titles => JSON.stringify([...document.querySelectorAll('[data-testid=\"todo-row\"] [data-testid=\"row-title\"]')]"
                ".map(e => e.textContent.trim())) === JSON.stringify(titles)", arg=[t["title"] for t in body])

    def _learn(self, todo: Todo) -> None:
        shown = self.browser.page.locator(ROWS).evaluate_all("els => els.map(e => e.dataset.id)")
        taken = set(self._app_ids.values())
        self._app_ids[cast(str, todo.id)] = next(i for i in shown if i not in taken)

    def _row(self, todo: Todo) -> Any:
        found = self.browser.page.locator(f'{ROWS}[data-id="{self._app_ids.get(todo.id or "")}"]')
        return found.first if found.count() else None

    def _fill(self, form: type[AddForm] | type[EditForm], title: str | None = None, description: str | None = None,
              due: date | str | None = None, assignee: str | None = None, clear_due: bool = False) -> None:
        b = self.browser
        for component, value in ((form.title, title), (form.description, description), (form.assignee, assignee)):
            if value is not None:
                b.fill(component, value, form.root)
        if clear_due and issubclass(form, EditForm):
            b.press(form.clear_due, within=form.root)
        elif due is not None:
            b.fill(form.due, due.isoformat() if isinstance(due, date) else str(due), form.root)

    def _save(self, form: type[AddForm] | type[EditForm], method: str) -> Outcome:
        b = self.browser
        if b.disabled(form.save, form.root):
            if not b.value(form.title, form.root).strip():
                return Refusal("Title is required", 0)
            return Refusal(b.locate(form.save, within=form.root).get_attribute("title") or "Save is disabled", 0)
        with b.answered(answer("GET", "/todos"), refusal(method, "/todos")) as got:
            b.press(form.save, within=form.root)
        if got.refused:
            b.wait_for(form.error, within=form.root)
            return Refusal(b.text(form.error, within=form.root), 0)
        self._shows(got)
        return Done(self.rows())

    def _add(self, todo: Todo) -> Outcome:
        self._fill(AddForm, todo.title or "", todo.description or "", todo.due_on or "", todo.assignee or "")
        outcome = self._save(AddForm, "POST")
        if isinstance(outcome, Done) and todo.id is not None:
            self._shown[todo.id] = todo.but()
            self._learn(todo)
        return outcome

    def _update(self, todo: Todo) -> Outcome:
        li = self._row(todo)
        shown = self._shown.get(todo.id or "")
        if li is None or shown is None:
            return Refusal("Not found", 404)
        self.browser.in_row(li, ListPage.edit).click()
        was_due = _typed(shown.due_on)
        now_due = _typed(todo.due_on)
        try:
            self._fill(
                EditForm,
                None if todo.title == shown.title else (todo.title or ""),
                None if todo.description == shown.description else (todo.description or ""),
                None if now_due == was_due or now_due is None else now_due,
                None if todo.assignee == shown.assignee else (todo.assignee or ""),
                clear_due=was_due is not None and now_due is None,
            )
        except CannotReach:
            self.browser.press(EditForm.cancel, within=EditForm.root)
            raise
        outcome = self._save(EditForm, "PUT")
        if isinstance(outcome, Refusal):
            self.browser.press(EditForm.cancel, within=EditForm.root)
        else:
            self._shown[cast(str, todo.id)] = todo.but()
        return outcome

    def _remove(self, todo: Todo) -> Outcome:
        li = self._row(todo)
        if li is None:
            return Refusal("Not found", 404)
        remove = self.browser.in_row(li, ListPage.remove)
        if remove.is_disabled():
            return Refusal(remove.get_attribute("title") or "Remove is disabled", 0)
        remove.click()
        with self.browser.answered(answer("GET", "/todos"), refusal("DELETE", "/todos")) as got:
            self.browser.press(RemoveDialog.confirm)
        if got.refused:
            message = self.browser.text(RemoveDialog.question)
            self.browser.press(RemoveDialog.keep)
            return Refusal(message, 0)
        self._shows(got)
        self._shown.pop(cast(str, todo.id), None)
        self._app_ids.pop(cast(str, todo.id), None)
        return Done(self.rows())

    def _find(self, q: Query) -> Outcome:
        b = self.browser
        if b.visible(ListPage.offline):
            return Refusal(b.text(ListPage.offline), 0)
        if (q.status or "") not in b.offered(ListPage.status):
            return Refusal("Unknown status", 0)
        wanted = {"text": q.text or "", "assignee": q.assignee or "", "status": q.status or ""}
        if not any(wanted.values()):
            return Done(self.rows())
        with self._listed(**wanted) as got:
            for component, value in ((ListPage.search, wanted["text"]), (ListPage.assignee, wanted["assignee"]), (ListPage.status, wanted["status"])):
                b.fill(component, value)
        refused = Refusal(got.json()["error"], got.response.status) if got.refused else None
        found = self.rows()
        with self._listed(text="", assignee="", status=""):
            for component in (ListPage.search, ListPage.assignee, ListPage.status):
                b.fill(component, "")
        return refused or Done(found)

    def save_was_disabled_while_saving(self, title: str) -> str | None:
        """Presses Save twice while the first request is out, then removes what
        landed so the list is as the journey left it. Returns what went wrong."""
        b = self.browser
        b.fill(AddForm.title, title, AddForm.root)
        save = b.locate(AddForm.save, within=AddForm.root)
        with self._listed() as got, b.holding(request("POST", "/todos")):
            with b.sent(request("POST", "/todos")):
                save.click()
            b.wait_for(AddForm.saving, within=AddForm.root)
            disabled = save.is_disabled()
            save.click(force=True, no_wait_after=True)
        landed = [t for t in got.json() if t["title"] == title]
        wrong = None
        if not disabled:
            wrong = "Save stayed enabled while the request was out"
        elif len(landed) != 1:
            wrong = f"{len(landed)} todos landed, not one"
        elif b.value(AddForm.title, AddForm.root):
            wrong = "the title was not cleared after 201"
        page = b.page
        row = page.locator(ROWS).filter(has=page.locator('[data-testid="row-title"]', has_text=title)).first
        if row.count():
            b.in_row(row, ListPage.remove).click()
            with self._listed():
                b.press(RemoveDialog.confirm)
        return wrong

    def wrong_labels_in_edit(self, lang: str, todo: Todo) -> str | None:
        self.browser.in_row(self._row(todo), ListPage.edit).click()
        wrong = self.wrong_labels(lang, (EditForm,))
        self.browser.press(EditForm.cancel, within=EditForm.root)
        return wrong

    def wrong_labels_in_remove(self, lang: str, todo: Todo) -> str | None:
        self.browser.in_row(self._row(todo), ListPage.remove).click()
        wrong = self.wrong_labels(lang, (RemoveDialog,))
        self.browser.press(RemoveDialog.keep)
        return wrong

    def banner_shown(self) -> str | None:
        return None if self.browser.visible(ListPage.offline) else "no offline banner"

    def disabled(self, component: Any, row: Any = None) -> str | None:
        return super().disabled(component, None if row is None else self._row(row))

    add_save = AddForm.save
    remove = ListPage.remove
