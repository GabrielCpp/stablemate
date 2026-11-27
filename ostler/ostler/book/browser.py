"""A browser for the surfaces that are pages. Wraps Playwright behind the few
verbs a screen driver needs, so a book never imports Playwright itself.

Every wait is on an event: a request leaving, an answer arriving, a component
appearing, the rows an answer carries showing on screen. No wait is on a clock."""

from __future__ import annotations

import linecache
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, cast
from urllib.parse import urlsplit

from ostler.book.asked import Asked
from ostler.book.errors import BookError
from ostler.book.listjudge import ListJudge, ListReader, Unfed
from ostler.book.outcome import CannotReach, cut_by_limit
from ostler.book.pagedata import Handed, decode, on_route
from ostler.book.pagescripts import FIELDS
from ostler.book.screen import ROLES, Aspect, Component, Screen, Viewport
from ostler.book.wanted import Wanted
from ostler.qa.harness_host import load_harness_module

DEFAULT_SIZE = (1280, 720)


def known_callers() -> None:
    """Every frame below this call whose file is on no disk, such as `<frozen runpy>` under `python -m`, put in
    `linecache`. Playwright's sync API calls `inspect.stack` on every browser call, and `inspect` scans all of
    `sys.modules` for each frame it cannot place, so two such frames made each call several times slower."""
    frame = sys._getframe(1)
    while frame is not None:
        name = frame.f_code.co_filename
        if name not in linecache.cache and not os.path.exists(name):
            linecache.cache[name] = (0, None, [], name)
        frame = frame.f_back


class Held:
    def __init__(self, page: Any, routes: list[Any]):
        self.page = page
        self.routes = routes

    def arrived(self) -> None:
        """Returns once a request is held, answering the browser's events until then."""
        while not self.routes:
            self.page.evaluate("0")


@dataclass
class Received:
    response: Any = None

    @property
    def refused(self) -> bool:
        return self.response.status >= 400

    def json(self) -> Any:
        return self.response.json()


class Browser(ListReader):
    def __init__(
        self,
        base: str,
        lang: str = "",
        selector: str = '[data-testid="{id}"]',
        headless: bool = True,
        lang_query: str | None = "lang",
        timeout: float = 10_000,
        hang_guard: float = 600_000,
        locales: Mapping[str, str] | None = None,
    ):
        self.base = base.rstrip("/")
        self.lang = lang
        self.locales = locales or {}
        self.lang_query = lang_query
        self.selector = selector
        self.headless = headless
        self.timeout = timeout
        self.hang_guard = hang_guard
        self.video_dir: str | None = None
        self._pw: Any = None
        self._browser: Any = None
        self.page: Any = None
        self.context: Any = None
        self._seen: list[Any] = []
        self._prefix: str | None = None
        self._origins: tuple[str, ...] = ()
        self._noting: Any = None
        self._recording = ""
        self._began = 0.0
        self.lists = ListJudge()
        self.viewport: Viewport | None = None
        self._feeds: tuple[Wanted, ...] = ()
        self._kept: dict[Wanted, Any] = {}

    def start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BookError("a web book drives a browser through Playwright, which is not installed: "
                            "install ostler with the 'qa' extra and run `playwright install chromium`") from None

        known_callers()
        self._pw = sync_playwright().start()
        shared = load_harness_module("ostler_qa_shared_browser").connect(self._pw) if self.headless else None
        self._browser = shared or self._pw.chromium.launch(headless=self.headless)
        self._make()

    def stop(self) -> None:
        if self._pw is not None:
            self._browser.close()
            self._pw.stop()
            self._pw = None

    def _make(self, record: bool = False) -> None:
        options: dict[str, Any] = {}
        if self.lang:
            options["locale"] = self.locales.get(self.lang, self.lang)
        if record and self.video_dir is not None:
            options["record_video_dir"] = self.video_dir
        if self.viewport is not None:
            options["viewport"] = {"width": self.viewport.width, "height": self.viewport.height}
        self.context = self._browser.new_context(**options)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        self.page.on("framenavigated", self._navigated)
        self._began = time.monotonic()
        if self._prefix is not None:
            self.watching(self._prefix, self._origins)
        self._listen()

    def begin(self, name: str) -> None:
        """Starts a recording named `name` in a fresh context, when a video directory is set. The page is blank."""
        if self.video_dir is None:
            return
        self.context.close()
        self._recording = name
        self._make(record=True)

    def offset(self) -> float | None:
        """Seconds from the start of the recording to now, or None when nothing is recording."""
        return time.monotonic() - self._began if self._recording else None

    def finish(self, keep: bool) -> str:
        """Ends the recording. The video is kept as `<video_dir>/<name>.webm` and its path returned, or deleted."""
        if not self._recording or self.video_dir is None:
            return ""
        name, self._recording = self._recording, ""
        video = self.page.video
        self.context.close()
        written = video.path()
        kept = ""
        if keep:
            kept = os.path.join(self.video_dir, re.sub(r"[^A-Za-z0-9_.-]+", "-", name) + ".webm")
            os.replace(written, kept)
        else:
            os.remove(written)
        self._make()
        return kept

    def watching(self, prefix: str, origins: tuple[str, ...] = ()) -> None:
        """Records every request whose path starts with `prefix`, whichever page sends it. With `origins`, only a
        request to one of them counts, so a call to a third party such as an error reporter is never the app's."""
        self._prefix = prefix
        self._origins = origins
        if self._noting is self.context:
            return
        self._noting = self.context

        def note(req: Any) -> None:
            parts = urlsplit(req.url)
            if self._prefix is None or not parts.path.startswith(self._prefix):
                return
            if not self._origins or f"{parts.scheme}://{parts.netloc}" in self._origins:
                self._seen.append(req)

        self.context.on("request", note)

    def feeding(self, screens: tuple[type[Screen], ...]) -> None:
        """Keeps, for each request a list of these screens is given by, the last answer the page receives."""
        self.lists.feeding(screens)
        self._feeds = tuple(c.lists.given for screen in screens for c in screen.components()
                            if c.lists is not None and c.lists.given is not None and not isinstance(c.lists.given, (Handed, Asked)))
        if self.context is not None:
            self._listen()

    def _listen(self) -> None:
        if not self._feeds:
            return

        def keep(response: Any) -> None:
            for wanted in self._feeds:
                if wanted(response.request):
                    self._kept[wanted] = response

        self.context.on("response", keep)

    def _navigated(self, frame: Any) -> None:
        if frame == self.page.main_frame:
            self.lists.forget_picks()

    def _judge(self, component: Component, shown: list[str], selected: str) -> None:
        self.lists.judge(component, shown, selected, self.lang, self._feed)

    def _feed(self, component: Component, name: str) -> tuple[Any, str]:
        given = component.lists.given if component.lists is not None else None
        assert given is not None and not isinstance(given, Asked)
        if isinstance(given, Handed):
            return self._handed(given, name)
        kept = self._kept.get(given)
        if kept is None:
            raise Unfed(f"the page received no answer to {getattr(given, 'text', 'the request')} before the pick in {name}")
        return kept.json(), kept.url

    def _handed(self, given: Handed, name: str) -> tuple[Any, str]:
        """The data the app's server hands the page now open, asked again in the browser's own session."""
        path = urlsplit(self.page.url).path
        if not on_route(given.route, path):
            raise Unfed(f"the list {name} is {given.text}, and the page open is at {path}, not on {given.route}")
        url = f"{self.base}{path.rstrip('/')}/__data.json"
        answered = self.context.request.get(url)
        if not answered.ok:
            raise Unfed(f"the list {name} is {given.text}, and the app's server answered {answered.status} to GET {url}")
        try:
            return decode(answered.text()), self.page.url
        except BookError as unreadable:
            raise Unfed(f"the list {name} is {given.text}, and it cannot be read: {unreadable}") from None

    def taken(self) -> list[Any]:
        """The requests recorded since the last time this was asked."""
        seen, self._seen = self._seen, []
        return seen

    def open(self, route: str) -> None:
        query = "" if self.lang_query is None or not self.lang else f"?{self.lang_query}={self.lang}"
        self._kept.clear()
        self.page.goto(f"{self.base}{route}{query}")

    def _scope(self, within: Component | None) -> Any:
        if within is None:
            return self.page
        return self._find(self.page, within)

    @staticmethod
    def _named_form(scope: Any, name: str) -> Any:
        return (scope.get_by_role("form", name=name, exact=True)
                .or_(scope.get_by_role("group", name=name, exact=True))
                .or_(scope.get_by_role("region", name=name, exact=True)))

    def _find(self, scope: Any, component: Component) -> Any:
        if component.id is not None:
            return scope.locator(self.selector.format(id=component.id)).first
        assert component.label is not None
        name = component.label[self.lang]
        if component.kind == "form":
            return (self._named_form(scope, name)
                    .or_(scope.locator("form").filter(has=scope.get_by_role("heading", name=name, exact=True)))
                    .or_(scope.locator("form").filter(has=scope.get_by_role("button", name=name, exact=True)))).first
        if component.kind in ROLES:
            return scope.get_by_role(ROLES[component.kind], name=name, exact=True).first
        return scope.get_by_text(name, exact=True).first

    def locate(self, component: Component, row: str | None = None, within: Component | None = None) -> Any:
        scope = self._scope(within)
        if row is None:
            return self._find(scope, component)
        if component.id is None:
            return self._find(self.row(row, within), component)
        return scope.locator(self.selector.format(id=f"{component.id} {row}")).first

    def row(self, containing: str, within: Component | None = None) -> Any:
        """The smallest list item, table row or group whose text contains `containing`."""
        item = "li, tr, [role=group], [role=row]"
        smallest = self._scope(within).locator(f":is({item}):not(:has({item}))")
        return smallest.filter(has_text=containing).first

    def fill(self, component: Component, value: str, within: Component | None = None) -> None:
        """Types `value` into a field, text area or date, or picks it in a select, native or a popup of options;
        a select that does not offer it is a `CannotReach`."""
        found = self.locate(component, within=within)
        if component.kind != "select":
            try:
                found.fill(value)
            except Exception as rejected:
                if "Malformed value" not in str(rejected) and "Cannot type text into" not in str(rejected):
                    raise
                raise CannotReach(f"{component.found_by(self.lang)} does not take {value!r}") from None
            try:
                kept = found.input_value()
            except Exception:
                return
            if len(kept) < len(value) and value.startswith(kept):
                raise CannotReach(cut_by_limit(component.found_by(self.lang), len(kept), len(value)))
            return
        if not self._native(found):
            self._pick_in_popup(component, found, value)
            return
        self._judge_native(component, found)
        offered = found.evaluate("el => [...el.options].map(o => o.value)")
        if value not in offered:
            raise CannotReach(f"{component.found_by(self.lang)} offers only {offered}")
        found.select_option(value)

    def press(self, component: Component, row: str | None = None, within: Component | None = None) -> None:
        self.locate(component, row, within).click()

    def text(self, component: Component, row: str | None = None, within: Component | None = None) -> str:
        return self.locate(component, row, within).inner_text()

    def value(self, component: Component, within: Component | None = None) -> str:
        return self.locate(component, within=within).input_value()

    @staticmethod
    def _native(found: Any) -> bool:
        return bool(found.evaluate("el => el.tagName === 'SELECT'"))

    @staticmethod
    def _texts(found: Any) -> list[str]:
        return found.evaluate("el => [...el.options].map(o => o.text)")

    def _open(self, found: Any) -> Any:
        found.click()
        controlled = found.get_attribute("aria-controls") or found.get_attribute("aria-owns")
        if controlled:
            listbox = self.page.locator(f'[id="{controlled}"]')
        else:
            listbox = self.page.get_by_role("listbox").first
        listbox.wait_for(state="visible")
        return listbox

    def _close(self, listbox: Any) -> None:
        self.page.keyboard.press("Escape")
        listbox.wait_for(state="hidden")

    @staticmethod
    def _entries(listbox: Any) -> list[tuple[str, str]]:
        return [tuple(entry) for entry in listbox.evaluate(
            """el => [...el.querySelectorAll('[role=option]')].map(o => {
                const label = o.innerText.trim();
                const value = o.getAttribute('data-value');
                return [value === null ? label : value, label];
            })""")]

    def _judge_native(self, component: Component, found: Any) -> None:
        if component.lists is not None:
            chosen = found.evaluate("el => el.selectedOptions.length ? el.selectedOptions[0].text : ''")
            self._judge(component, self._texts(found), chosen)

    def _judge_popup(self, component: Component, found: Any, listbox: Any, entries: list[tuple[str, str]]) -> None:
        if component.lists is not None:
            marked = listbox.evaluate(
                """el => { const o = el.querySelector('[role=option][aria-selected=true]'); return o ? o.innerText.trim() : null; }""")
            self._judge(component, [label for _, label in entries], found.inner_text().strip() if marked is None else marked)

    def _pick_in_popup(self, component: Component, found: Any, value: str) -> None:
        listbox = self._open(found)
        entries = self._entries(listbox)
        self._judge_popup(component, found, listbox, entries)
        values = [entry for entry, _ in entries]
        labels = [label for _, label in entries]
        if value in values:
            index = values.index(value)
        elif value in labels:
            index = labels.index(value)
        else:
            self._close(listbox)
            raise CannotReach(f"{component.found_by(self.lang)} offers only {values}")
        listbox.locator("[role=option]").nth(index).click()
        listbox.wait_for(state="hidden")

    def fields(self, component: Component, within: Component | None = None) -> list[tuple[str, str]]:
        """The labelled controls of a form, in document order, each as its accessible name and its ARIA role, judged
        against what the book states of the form."""
        shown = [(label, role) for label, role in self.locate(component, within=within).evaluate(FIELDS)]
        if component.lists is not None:
            self._judge(component, cast("list[Any]", shown), "")
        return shown

    def labels(self, component: Component, within: Component | None = None) -> list[str]:
        """The texts a select shows, in order, judged against what the book states of its list. A popup is opened to
        read them and closed again. A form gives the names of its fields, read and judged as `fields` does."""
        if component.kind == "form":
            return [label for label, _ in self.fields(component, within)]
        found = self.locate(component, within=within)
        if self._native(found):
            self._judge_native(component, found)
            return self._texts(found)
        listbox = self._open(found)
        entries = self._entries(listbox)
        self._judge_popup(component, found, listbox, entries)
        self._close(listbox)
        return [label for _, label in entries]

    def offered(self, component: Component, within: Component | None = None) -> list[str]:
        """The values a select offers, in order. A popup is opened to read them and closed again."""
        found = self.locate(component, within=within)
        if self._native(found):
            return found.evaluate("el => [...el.options].map(o => o.value)")
        listbox = self._open(found)
        values = [value for value, _ in self._entries(listbox)]
        self._close(listbox)
        return values

    def disabled(self, component: Component, within: Component | None = None) -> bool:
        return self.locate(component, within=within).is_disabled()

    def visible(self, component: Component, within: Component | None = None) -> bool:
        found = self.locate(component, within=within)
        return bool(found.count()) and found.is_visible()

    def wait_for(self, component: Component, state: str = "visible", within: Component | None = None) -> None:
        """Waits until the component is `visible` or `hidden`, `attached` or `detached`."""
        self.locate(component, within=within).wait_for(state=state)

    def resize(self, viewport: Viewport | None) -> None:
        """Lays the page out at the viewport's size, or at the browser's own size when None."""
        if viewport == self.viewport:
            return
        width, height = (viewport.width, viewport.height) if viewport is not None else DEFAULT_SIZE
        self.page.set_viewport_size({"width": width, "height": height})
        self.viewport = viewport

    def read(self, component: Component, aspect: Aspect, within: Component | None = None) -> str:
        """The state the component shows for the aspect, as text: an attribute's value, '' when it has none, 'true' or
        'false' for a check, the name of the picked choice."""
        found = self.locate(component, within=within)
        if aspect.attribute:
            return found.get_attribute(aspect.attribute) or ""
        if aspect.name == "checked":
            return "true" if found.is_checked() else "false"
        return self._picked(found)

    def _picked(self, found: Any) -> str:
        if found.evaluate("el => el.tagName") == "SELECT":
            return found.evaluate("el => el.selectedIndex < 0 ? '' : el.options[el.selectedIndex].text").strip()
        checked = found.get_by_role("radio", checked=True)
        if checked.count():
            return self.accessible_name(checked.first)
        return found.inner_text().strip()

    def holds(self, component: Component, aspect: Aspect, value: str, within: Component | None = None) -> str | None:
        """Waits, by the page's own assertion wait, until the component shows `value` for the aspect. None when it does,
        else what it showed."""
        from playwright.sync_api import expect

        found = self.locate(component, within=within)
        try:
            if aspect.attribute:
                expect(found).to_have_attribute(aspect.attribute, value, timeout=self.timeout)
            elif aspect.name == "checked":
                expect(found).to_be_checked(checked=value == "true", timeout=self.timeout)
            elif found.evaluate("el => el.tagName") == "SELECT":
                expect(found.locator("option:checked")).to_have_text(value, timeout=self.timeout)
            elif found.get_by_role("radio").count():
                expect(found.get_by_role("radio", checked=True)).to_have_accessible_name(value, timeout=self.timeout)
            else:
                expect(found).to_contain_text(value, timeout=self.timeout)
        except AssertionError:
            return f"{component.found_by(self.lang)} is {aspect.name} {self.read(component, aspect, within)!r}, wanted {value!r}"
        return None

    def wrong_labels(self, lang: str, screens: tuple[type[Screen], ...]) -> str | None:
        """Every visible component whose accessible name is not its label in `lang`, one per line, or None."""
        wrong = []
        for screen in screens:
            for component in screen.components():
                if component.label is None or component.per_row or component.kind == "spinner":
                    continue
                if not self.visible(component, screen.root):
                    continue
                if component.kind == "form" and component.id is not None and not self._named_form(self._scope(screen.root), component.label[lang]).count():
                    wrong.append(f"{screen.__name__}.{component.found_by(lang)}: the form has no accessible name {component.label[lang]!r}, "
                                 "it is found only by its id: give it aria-label or aria-labelledby")
                    continue
                name = self.accessible_name(self.locate(component, within=screen.root))
                if component.label[lang] not in name:
                    wrong.append(f"{screen.__name__}.{component.found_by(lang)}: saw {name!r}, wanted {component.label[lang]!r}")
        return "\n".join(wrong) or None

    @staticmethod
    def accessible_name(locator: Any) -> str:
        return locator.evaluate("""el => {
            const byId = el.id && document.querySelector(`label[for="${el.id}"]`);
            if (byId) return byId.textContent;
            if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
            if (el.getAttribute('aria-labelledby')) return document.getElementById(el.getAttribute('aria-labelledby'))?.textContent || '';
            if (el.closest('label')) return el.closest('label').textContent;
            return el.textContent || '';
        }""").strip()

    def on(self, screen: Any) -> "Browser.View":
        return Browser.View(self, screen.root)

    class View:
        def __init__(self, browser: "Browser", root: Component | None):
            self.browser = browser
            self.root = root

        def locate(self, component: Component, row: str | None = None) -> Any:
            return self.browser.locate(component, row, within=self.root)

    def in_row(self, row_locator: Any, component: Component) -> Any:
        return self._find(row_locator, component)

    @contextmanager
    def answered(self, *wanted: Wanted) -> Iterator[Received]:
        """Runs the body, then waits for the first answer one of `wanted`
        matches, body included. The answer is in the result; what the page
        does with it is the surface's to wait for."""
        received = Received()
        with self.page.expect_response(lambda r: any(w(r) for w in wanted), timeout=self.hang_guard) as info:
            yield received
        received.response = info.value
        received.response.body()

    @contextmanager
    def sent(self, wanted: Wanted) -> Iterator[None]:
        """Runs the body, then waits for the request `wanted` to leave."""
        with self.page.expect_request(wanted, timeout=self.hang_guard):
            yield

    @contextmanager
    def holding(self, wanted: Wanted) -> Iterator["Held"]:
        """Keeps every request `wanted` from reaching the server until the body
        ends, so a phase the app leaves as soon as the answer lands can be
        observed. A request that has left the page is not yet held: the body
        calls `arrived()` on the result to wait until it is."""
        held: list[Any] = []
        live = [True]

        def hold(route: Any) -> None:
            if live[0] and wanted(route.request):
                held.append(route)
            else:
                route.continue_()

        self.page.route("**/*", hold)
        try:
            yield Held(self.page, held)
        finally:
            live[0] = False
            for route in held:
                route.continue_()

    def set_offline(self, offline: bool) -> None:
        self.context.set_offline(offline)
