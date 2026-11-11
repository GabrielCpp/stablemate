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
from typing import Any, Callable, Iterator
from urllib.parse import parse_qsl, urlsplit

from ostler.book.errors import BookError
from ostler.book.outcome import CannotReach
from ostler.book.screen import ROLES, Component, Screen

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
        lang: str = "en",
        selector: str = '[data-testid="{id}"]',
        headless: bool = True,
        lang_query: str | None = "lang",
        timeout: float = 10_000,
    ):
        self.base = base.rstrip("/")
        self.lang = lang
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
        options: dict[str, Any] = {"locale": "fr-CA" if self.lang == "fr" else "en-US"}
        if record and self.video_dir is not None:
            options["record_video_dir"] = self.video_dir
        self.context = self._browser.new_context(**options)
        self.page = self.context.new_page()
        self.page.set_default_timeout(self.timeout)
        self._began = time.monotonic()
        if self._prefix is not None:
            self.watching(self._prefix)

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

    def taken(self) -> list[Any]:
        """The requests recorded since the last time this was asked."""
        seen, self._seen = self._seen, []
        return seen

    def open(self, route: str) -> None:
        query = "" if self.lang_query is None else f"?{self.lang_query}={self.lang}"
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
        """Types `value` into a field, text area or date, or picks it in a select; a select that does not offer
        it is a `CannotReach`."""
        found = self.locate(component, within=within)
        if component.kind != "select":
            found.fill(value)
            return
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

    def offered(self, component: Component, within: Component | None = None) -> list[str]:
        return self.locate(component, within=within).evaluate("el => [...el.options].map(o => o.value)")

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
