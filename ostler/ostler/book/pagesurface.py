"""The generic surface of a web app: a browser on the app's screens. The book's
surface keeps only what is specific to its app, which is how each interaction
is performed and what the rows read as."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit

from ostler.book.browser import Browser
from ostler.book.environment import Environment
from ostler.book.errors import BookError
from ostler.book.pagedata import on_route
from ostler.book.screen import Component, Is, Phase, Screen, Viewport


class PageSurface:
    """Subclass per web app. `host` names the environment host that serves the
    pages. The screens say which requests the page may send, so a request no
    screen declares fails the step that made it. `locales` gives the browser
    locale of a language whose name alone is not enough."""

    name = "web"
    host = "web"
    locales: dict[str, str] = {}
    routed = True

    def __init__(self, environment: Environment, screens: tuple[type[Screen], ...], lang: str = ""):
        self.screens = screens
        self.lang = lang
        self.environment = environment
        self.browser = self.drive(environment, lang)

    def drive(self, environment: Environment, lang: str) -> Any:
        """What the surface drives: a browser on the host's pages. A mobile surface drives a device instead."""
        return Browser(environment.address(self.host), lang, locales=self.locales)

    def start(self) -> None:
        self.browser.feeding(self.screens)
        self.browser.start()
        api = next((screen.api for screen in self.screens if screen.api), "")
        if api:
            self.browser.watching(api, self.origins())

    def origins(self) -> tuple[str, ...]:
        """The origins of the hosts the environment declares. A request to any other host is not the app's."""
        found: list[str] = []
        for host in self.environment.hosts:
            try:
                parts = urlsplit(self.environment.address(host))
            except (BookError, RuntimeError, OSError):
                continue
            if parts.scheme and parts.netloc:
                found.append(f"{parts.scheme}://{parts.netloc}")
        return tuple(found)

    def stop(self) -> None:
        self.browser.stop()

    def record_to(self, directory: str) -> None:
        """Records a video of each journey and cell arrangement into `directory`."""
        self.browser.video_dir = directory

    def record(self, name: str) -> None:
        """Starts the video named `name` and opens the first screen in it."""
        if self.browser.video_dir is not None:
            self.browser.begin(name)
            self.open()

    def finish(self, keep: bool) -> str:
        """Ends the video and returns its path, or "" when it was not kept."""
        return self.browser.finish(keep)

    def offset(self) -> float | None:
        """Where the video is now, in seconds from its start."""
        return self.browser.offset()

    def open(self) -> None:
        """Opens the app's first screen and waits until it has shown what it fetched."""
        raise NotImplementedError

    def restore(self) -> None:
        """Puts the app behind the pages back to its first state."""
        raise NotImplementedError

    def reset(self) -> None:
        self.browser.set_offline(False)
        if self.browser.page is not None:
            self.browser.page.goto("about:blank")
            self.browser.resize(None)
        self.restore()
        self.open()

    @property
    def viewport(self) -> Viewport | None:
        """The size the page is laid out at, None for the browser's own."""
        return self.browser.viewport

    def fit(self, viewport: Viewport | None) -> None:
        """Lays the page out at the size the next step plays at."""
        self.browser.resize(viewport)

    def phase_faults(self, screen: type[Screen], phase: Phase, states: tuple[tuple[Is, str], ...]) -> list[str]:
        """What the page shows against a phase that holds now: each component it shows that is hidden, each it hides that
        is shown, each it disables that is enabled, and each state that reads otherwise. Each waits by the page's own wait."""
        faults = []
        within = screen.root
        for component in phase.shows:
            try:
                self.browser.wait_for(component, "visible", within)
            except self.timeouts():
                faults.append(f"{component.found_by(self.lang)} is not shown")
        for component in phase.hides:
            try:
                self.browser.wait_for(component, "hidden", within)
            except self.timeouts():
                faults.append(f"{component.found_by(self.lang)} is shown")
        for component in phase.disabled:
            if not self.browser.disabled(component, within):
                faults.append(f"{component.found_by(self.lang)} is enabled")
        for claim, value in states:
            fault = self.browser.holds(claim.component, claim.aspect, value, within)
            if fault is not None:
                faults.append(fault)
        return faults

    def set_lang(self, lang: str) -> None:
        changed = lang != self.lang
        self.lang = lang
        self.browser.lang = lang
        if changed and self.browser.page is not None:
            self.open()

    def marks(self, screen: type[Screen]) -> tuple[str, Component | None]:
        """What tells the person is on the screen: its route and its root component, each empty when the screen states none.
        A screen inside another with no root of its own is told by its host."""
        if screen.inside is not None:
            return ("", screen.root) if screen.root is not None else self.marks(screen.inside)
        return (screen.route if self.routed else "", screen.root)

    def path(self) -> str:
        """The path of the page's address, below the base address, with no query."""
        return self.below(urlsplit(self.browser.page.url).path)

    def below(self, path: str) -> str:
        base = urlsplit(self.browser.base).path.rstrip("/")
        if base and (path == base or path.startswith(base + "/")):
            return path[len(base):] or "/"
        return path

    def on(self, screen: type[Screen]) -> bool | None:
        """Whether the person is on the screen now: the path of the page matches its route and its root is visible, each
        when the screen states it. None when it states neither."""
        route, root = self.marks(screen)
        if not route and root is None:
            return None
        return (not route or on_route(route, self.path())) and (root is None or self.browser.visible(root))

    def arrive(self, screen: type[Screen]) -> bool | None:
        """Waits, by the browser's own event wait and limit, until the person is on the screen. Returns whether they
        came, or None when the screen states nothing to tell it by."""
        route, root = self.marks(screen)
        if not route and root is None:
            return None
        try:
            if route:
                self.browser.page.wait_for_url(lambda url: on_route(route, self.below(urlsplit(url).path)))
            if root is not None:
                self.browser.wait_for(root)
        except self.timeouts():
            return False
        return True

    def timeouts(self) -> tuple[type[Exception], ...]:
        """What the browser raises when its wait runs out."""
        from playwright.sync_api import TimeoutError as Timeout

        return (Timeout,)

    def strays(self) -> list[str]:
        """The product API requests the page sent that no screen declares."""
        declared = [wanted for screen in self.screens for wanted in screen.sends]
        return [f"{r.method} {urlsplit(r.url).path}" for r in self.browser.taken() if not any(w(r) for w in declared)]

    def list_faults(self) -> list[str]:
        """The lists a pick found different from what the book derives."""
        return self.browser.list_faults()

    def expecting(self, expectations: Mapping[str, tuple[Any, ...]], asked: Mapping[str, Any] | None = None) -> None:
        """Hands the browser, per list, who must be offered and who must not, and the answers of the backends that feed
        lists, for the picks of one step."""
        self.browser.expecting(expectations, asked)

    def lists_read(self) -> frozenset[str]:
        return self.browser.lists_read()

    def claims_judged(self) -> dict[str, frozenset[str]]:
        return self.browser.claims_judged()

    def wrong_labels(self, lang: str, screens: tuple[type[Screen], ...] | None = None) -> str | None:
        return self.browser.wrong_labels(lang, self.screens if screens is None else screens)

    def disabled(self, component: Any, row: Any = None) -> str | None:
        """None when the component is disabled, else what is wrong. `row` is the locator of the row it sits in."""
        found = self.browser.locate(component) if row is None else self.browser.in_row(row, component)
        return None if found.is_disabled() else f"{component.found_by(self.lang)} is enabled"
