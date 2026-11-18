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
from typing import Any, Callable, Iterator, Mapping, cast
from urllib.parse import parse_qsl, urlsplit

from ostler.book.asked import Asked
from ostler.book.errors import BookError
from ostler.book.listjudge import ListJudge, ListReader, Unfed
from ostler.book.outcome import CannotReach, cut_by_limit
from ostler.book.pagedata import Handed, decode, on_route
from ostler.book.screen import ROLES, Component, Screen

Wanted = Callable[[Any], bool]

FIELDS = """root => {
    const KINDS = ['textbox', 'spinbutton', 'combobox', 'checkbox', 'radiogroup', 'switch', 'slider', 'listbox'];
    const shown = (el) => el.checkVisibility ? el.checkVisibility() : !!el.offsetParent;
    const text = (el) => (el.textContent || '').replace(/\\s+/g, ' ').trim();
    const named = (el) => {
        const by = el.getAttribute('aria-labelledby');
        if (by) return by.split(/\\s+/).map((id) => document.getElementById(id)).filter(Boolean).map(text).join(' ');
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
        const set = el.closest('fieldset');
        const legend = set && set.querySelector('legend');
        if (el.getAttribute('role') === 'radiogroup' || el.type === 'radio') return legend ? text(legend) : '';
        if (el.labels && el.labels.length) return [...el.labels].map(text).join(' ');
        return (el.getAttribute('title') || el.getAttribute('placeholder') || '').trim();
    };
    const roleOf = (el) => {
        const given = (el.getAttribute('role') || '').split(/\\s+/)[0];
        if (given) return KINDS.includes(given) ? given : null;
        const tag = el.tagName;
        if (tag === 'TEXTAREA') return 'textbox';
        if (tag === 'SELECT') return el.multiple || el.size > 1 ? 'listbox' : 'combobox';
        if (tag !== 'INPUT') return null;
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        if (type === 'number') return 'spinbutton';
        if (type === 'checkbox') return 'checkbox';
        if (type === 'range') return 'slider';
        if (type === 'radio') return el.closest('[role=radiogroup]') ? null : 'radiogroup';
        return ['hidden', 'button', 'submit', 'reset', 'image', 'file', 'color'].includes(type) ? null : 'textbox';
    };
    const out = [], taken = [], groups = new Set();
    for (const el of root.querySelectorAll('*')) {
        if (!shown(el) || taken.some((outer) => outer.contains(el))) continue;
        const role = roleOf(el);
        if (role === null) continue;
        if (el.type === 'radio') {
            if (groups.has(el.name)) continue;
            groups.add(el.name);
        } else {
            taken.push(el);
        }
        out.push([named(el), role]);
    }
    return out;
}"""


def request(method: str, path: str, **query: str) -> Wanted:
    """Matches a request by verb, path (`/todos` also matches `/todos/{id}`, and a `{name}` in the path stands for
    one segment, as in `/projects/{id}/variants`) and the query parameters named; a parameter not sent counts as ''."""
    shape = "/".join("[^/]+" if re.fullmatch(r"\{[^{}/]+\}", part) else re.escape(part) for part in path.split("/"))
    template = re.compile(f"{shape}(/.*)?")

    def wanted(req: Any) -> bool:
        parts = urlsplit(req.url)
        on_path = template.fullmatch(parts.path) is not None
        params = dict(parse_qsl(parts.query, keep_blank_values=True))
        return req.method == method and on_path and all(params.get(k, "") == v for k, v in query.items())

    setattr(wanted, "text", " ".join([method, path, *(f"{k}={v}" for k, v in query.items())]))
    return wanted


def asked(thing: Any) -> Any:
    return getattr(thing, "request", thing)


def answer(method: str, path: str, **query: str) -> Wanted:
    """Matches the answer to such a request, whatever its status."""
    wanted = request(method, path, **query)
    return lambda response: wanted(asked(response))


def action(route: str, name: str) -> Wanted:
    """Matches the answer to the POST of the form action `name` of the page `route`, as `POST /?/add`."""

    def wanted(response: Any) -> bool:
        req = asked(response)
        parts = urlsplit(req.url)
        named = any(key == f"/{name}" for key, _ in parse_qsl(parts.query, keep_blank_values=True))
        return req.method == "POST" and on_route(route, parts.path) and named

    setattr(wanted, "text", f"POST {route}?/{name}")
    return wanted


def refusal(method: str, path: str) -> Wanted:
    """Matches a 4xx or 5xx answer to such a request."""
    wanted = request(method, path)
    return lambda response: wanted(asked(response)) and getattr(response, "status", 0) >= 400


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
        self._recording = ""
        self._began = 0.0
        self.lists = ListJudge()
        self._feeds: tuple[Wanted, ...] = ()
        self._kept: dict[Wanted, Any] = {}

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
