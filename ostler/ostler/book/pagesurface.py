"""The generic surface of a web app: a browser on the app's screens. The book's
surface keeps only what is specific to its app, which is how each interaction
is performed and what the rows read as."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ostler.book.browser import Browser
from ostler.book.environment import Environment
from ostler.book.screen import Screen


class PageSurface:
    """Subclass per web app. `host` names the environment host that serves the
    pages. The screens say which requests the page may send, so a request no
    screen declares fails the step that made it."""

    name = "web"
    host = "web"

    def __init__(self, environment: Environment, screens: tuple[type[Screen], ...], lang: str = "en"):
        self.screens = screens
        self.lang = lang
        self.browser = self.drive(environment, lang)

    def drive(self, environment: Environment, lang: str) -> Any:
        """What the surface drives: a browser on the host's pages. A mobile surface drives a device instead."""
        return Browser(environment.address(self.host), lang)

    def start(self) -> None:
        self.browser.start()
        api = next((screen.api for screen in self.screens if screen.api), "")
        if api:
            self.browser.watching(api)

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
        self.restore()
        self.open()

    def set_lang(self, lang: str) -> None:
        changed = lang != self.lang
        self.lang = lang
        self.browser.lang = lang
        if changed and self.browser.page is not None:
            self.open()

    def strays(self) -> list[str]:
        """The product API requests the page sent that no screen declares."""
        declared = [wanted for screen in self.screens for wanted in screen.sends]
        return [f"{r.method} {urlsplit(r.url).path}" for r in self.browser.taken() if not any(w(r) for w in declared)]

    def wrong_labels(self, lang: str, screens: tuple[type[Screen], ...] | None = None) -> str | None:
        return self.browser.wrong_labels(lang, self.screens if screens is None else screens)

    def disabled(self, component: Any, row: Any = None) -> str | None:
        """None when the component is disabled, else what is wrong. `row` is the locator of the row it sits in."""
        found = self.browser.locate(component) if row is None else self.browser.in_row(row, component)
        return None if found.is_disabled() else f"{component.found_by(self.lang)} is enabled"
