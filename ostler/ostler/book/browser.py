"""A browser for the surfaces that are pages. Wraps Playwright behind the few
verbs a screen driver needs, so a book never imports Playwright itself.

Every wait is on an event: a request leaving, an answer arriving, a component
appearing, the rows an answer carries showing on screen. No wait is on a clock."""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import parse_qsl, urlsplit

from ostler.book.errors import BookError
from ostler.book.outcome import CannotReach, cut_by_limit
from ostler.book.pagedata import Handed, decode, on_route
from ostler.book.screen import ROLES, Component, Lists, Screen

Wanted = Callable[[Any], bool]


def request(method: str, path: str, **query: str) -> Wanted:
    """Matches a request by verb, path (`/todos` also matches `/todos/{id}`)
    and the query parameters named; a parameter not sent counts as ''."""

    def wanted(req: Any) -> bool:
        parts = urlsplit(req.url)
        on_path = parts.path == path or parts.path.startswith(path + "/")
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        return req.method == method and on_path and all(params.get(k, "") == v for k, v in query.items())

    setattr(wanted, "text", " ".join([method, path, *(f"{k}={v}" for k, v in query.items())]))
    return wanted


def answer(method: str, path: str, **query: str) -> Wanted:
    """Matches the answer to such a request, whatever its status."""
    wanted = request(method, path, **query)
    return lambda response: wanted(response.request)


def action(route: str, name: str) -> Wanted:
    """Matches the answer to the POST of the form action `name` of the page `route`, as `POST /?/add`."""

    def wanted(response: Any) -> bool:
        req = response.request
        parts = urlsplit(req.url)
        named = any(key == f"/{name}" for key, _ in parse_qsl(parts.query, keep_blank_values=True))
        return req.method == "POST" and on_route(route, parts.path) and named

    setattr(wanted, "text", f"POST {route}?/{name}")
    return wanted


def refusal(method: str, path: str) -> Wanted:
    """Matches a 4xx or 5xx answer to such a request."""
    wanted = request(method, path)
    return lambda response: wanted(response.request) and response.status >= 400


@dataclass
class Received:
    response: Any = None

    @property
    def refused(self) -> bool:
        return self.response.status >= 400

    def json(self) -> Any:
        return self.response.json()


class Browser:
    def __init__(
        self,
        base: str,
        lang: str = "",
        selector: str = '[data-testid="{id}"]',
        headless: bool = True,
        lang_query: str | None = "lang",
        timeout: float = 10_000,
        locales: Mapping[str, str] | None = None,
    ):
        self.base = base.rstrip("/")
        self.lang = lang
        self.locales = locales or {}
        self.lang_query = lang_query
        self.selector = selector
        self.headless = headless
        self.timeout = timeout
        self.video_dir: str | None = None
        self._pw: Any = None
        self._browser: Any = None
        self.page: Any = None
        self.context: Any = None
        self._seen: list[Any] = []
        self._prefix: str | None = None
        self._recording = ""
        self._began = 0.0
        self._screens: tuple[type[Screen], ...] = ()
        self._feeds: tuple[Wanted, ...] = ()
        self._kept: dict[Wanted, Any] = {}
        self._faults: list[str] = []
        self._read: dict[str, set[str]] = {}
        self._picked: set[str] = set()
        self._expected: dict[str, tuple[Any, ...]] = {}

    def start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BookError("a web book drives a browser through Playwright, which is not installed: "
                            "install ostler with the 'qa' extra and run `playwright install chromium`") from None

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
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
        self.context = self._browser.new_context(**options)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        self.page.on("framenavigated", self._navigated)
        self._began = time.monotonic()
        if self._prefix is not None:
            self.watching(self._prefix)
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

    def watching(self, prefix: str) -> None:
        """Records every request whose path starts with `prefix`, whichever page sends it."""
        self._prefix = prefix

        def note(req: Any) -> None:
            if urlsplit(req.url).path.startswith(prefix):
                self._seen.append(req)

        self.context.on("request", note)

    def feeding(self, screens: tuple[type[Screen], ...]) -> None:
        """Keeps, for each request a list of these screens is given by, the last answer the page receives."""
        self._screens = screens
        self._feeds = tuple(c.lists.given for screen in screens for c in screen.components()
                            if c.lists is not None and c.lists.given is not None and not isinstance(c.lists.given, Handed))
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

    def list_faults(self) -> list[str]:
        """The differences found between a list and what the book derives since the last time this was asked."""
        faults, self._faults = self._faults, []
        return faults

    def lists_read(self) -> frozenset[str]:
        """The lists, by screen and attribute, a pick has judged."""
        return frozenset(self._read)

    def claims_judged(self) -> dict[str, frozenset[str]]:
        """For each list a pick has judged, the claims it judged: derived, always, never, entries, picked."""
        return {name: frozenset(claims) for name, claims in self._read.items()}

    def _navigated(self, frame: Any) -> None:
        if frame == self.page.main_frame:
            self._picked.clear()

    def _named(self, component: Component) -> str:
        for screen in self._screens:
            for name, found in screen.attributes():
                if found is component:
                    return f"{screen.__name__}.{name}"
        return component.found_by(self.lang)

    def expecting(self, expectations: Mapping[str, tuple[Any, ...]]) -> None:
        """Hands over, for each list by screen and attribute, the texts it must show and the texts it must not, and
        when the list's picked entry is a function, the label it returns, for the picks that follow. An empty mapping
        drops them."""
        self._expected = dict(expectations)

    def _judge(self, component: Component, shown: list[str], selected: str) -> None:
        lists = component.lists
        assert lists is not None
        name = self._named(component)
        judged = self._read.setdefault(name, set())
        if lists.derived is not None:
            judged.add("derived")
            self._judge_derived(component, name, shown)
        self._judge_entries(lists, name, shown)
        if lists.entries:
            judged.add("entries")
        self._judge_picked(lists, name, selected)
        if name not in self._picked and (lists.picked is not None and (not callable(lists.picked) or len(self._expected.get(name, ())) > 2)):
            judged.add("picked")
        self._picked.add(name)
        belong, never = self._expected.get(name, ([], []))[:2]
        if lists.always is not None and name in self._expected:
            judged.add("always")
        if lists.never is not None and name in self._expected:
            judged.add("never")
        missing = [text for text in dict.fromkeys(belong) if text not in shown]
        if missing:
            self._faults.append(f"the list {name} misses {missing}, which belong in it")
        forbidden = [text for text in dict.fromkeys(never) if text in shown]
        if forbidden:
            self._faults.append(f"the list {name} shows {forbidden}, which must never be in it")

    def _judge_entries(self, lists: Lists, name: str, shown: list[str]) -> None:
        head = lists.labels(self.lang)
        entries = shown[len(head):] if shown[:len(head)] == head else shown
        for rule in lists.entries:
            said = (rule.__doc__ or "").strip().splitlines()[0]
            try:
                broken = rule(entries)
            except Exception as crash:
                self._faults.append(f"the list {name} cannot judge \"{said}\": {type(crash).__name__}: {crash}")
                continue
            self._faults += [f"the list {name} breaks \"{said}\": {why}" for why in broken]

    def _judge_picked(self, lists: Lists, name: str, selected: str) -> None:
        if name in self._picked or lists.picked is None:
            return
        expected = self._expected.get(name, ())
        wanted = lists.label_picked(self.lang) if not callable(lists.picked) else expected[2] if len(expected) > 2 else None
        if wanted is not None and selected != wanted:
            self._faults.append(f"the list {name} has {selected!r} selected before the pick, the book says {wanted!r}")

    def _judge_derived(self, component: Component, name: str, shown: list[str]) -> None:
        lists = component.lists
        assert lists is not None and lists.given is not None and lists.derived is not None
        if isinstance(lists.given, Handed):
            body = self._handed(lists.given, name)
            if body is None:
                return
        else:
            kept = self._kept.get(lists.given)
            if kept is None:
                self._faults.append(f"the page received no answer to {getattr(lists.given, 'text', 'the request')} "
                                    f"before the pick in {name}")
                return
            body = kept.json()
        derived = [*lists.labels(self.lang), *lists.derived(body)]
        if shown != derived:
            self._faults.append(f"the list {name} shows {shown}, the book derives {derived}")

    def _handed(self, given: Handed, name: str) -> Any:
        """The data the app's server hands the page now open, asked again in the browser's own session, or None after
        a fault says why it could not be read."""
        path = urlsplit(self.page.url).path
        if not on_route(given.route, path):
            self._faults.append(f"the list {name} is {given.text}, and the page open is at {path}, not on {given.route}")
            return None
        url = f"{self.base}{path.rstrip('/')}/__data.json"
        answered = self.context.request.get(url)
        if not answered.ok:
            self._faults.append(f"the list {name} is {given.text}, and the app's server answered {answered.status} to GET {url}")
            return None
        try:
            return decode(answered.text())
        except BookError as unreadable:
            self._faults.append(f"the list {name} is {given.text}, and it cannot be read: {unreadable}")
            return None

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

    def _find(self, scope: Any, component: Component) -> Any:
        if component.id is not None:
            return scope.locator(self.selector.format(id=component.id)).first
        assert component.label is not None
        name = component.label[self.lang]
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
        if component.lists is not None:
            chosen = found.evaluate("el => el.selectedOptions.length ? el.selectedOptions[0].text : ''")
            self._judge(component, self._texts(found), chosen)
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

    def _pick_in_popup(self, component: Component, found: Any, value: str) -> None:
        listbox = self._open(found)
        entries = self._entries(listbox)
        if component.lists is not None:
            marked = listbox.evaluate(
                """el => { const o = el.querySelector('[role=option][aria-selected=true]'); return o ? o.innerText.trim() : null; }""")
            self._judge(component, [label for _, label in entries], found.inner_text().strip() if marked is None else marked)
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

    def labels(self, component: Component, within: Component | None = None) -> list[str]:
        """The texts a select shows, in order. A popup is opened to read them and closed again."""
        found = self.locate(component, within=within)
        if self._native(found):
            return self._texts(found)
        listbox = self._open(found)
        shown = [label for _, label in self._entries(listbox)]
        self._close(listbox)
        return shown

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

    def wrong_labels(self, lang: str, screens: tuple[type[Screen], ...]) -> str | None:
        """Every visible component whose accessible name is not its label in `lang`, one per line, or None."""
        wrong = []
        for screen in screens:
            for component in screen.components():
                if component.label is None or component.per_row or component.kind == "spinner":
                    continue
                if not self.visible(component, screen.root):
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
        with self.page.expect_response(lambda r: any(w(r) for w in wanted)) as info:
            yield received
        received.response = info.value
        received.response.body()

    @contextmanager
    def sent(self, wanted: Wanted) -> Iterator[None]:
        """Runs the body, then waits for the request `wanted` to leave."""
        with self.page.expect_request(wanted):
            yield

    @contextmanager
    def holding(self, wanted: Wanted) -> Iterator[None]:
        """Keeps every request `wanted` from reaching the server until the body
        ends, so a phase the app leaves as soon as the answer lands can be
        observed."""
        held: list[Any] = []

        def hold(route: Any) -> None:
            if wanted(route.request):
                held.append(route)
            else:
                route.continue_()

        self.page.route("**/*", hold)
        try:
            yield
        finally:
            for route in held:
                route.continue_()
            self.page.unroute("**/*", hold)

    def set_offline(self, offline: bool) -> None:
        self.context.set_offline(offline)
