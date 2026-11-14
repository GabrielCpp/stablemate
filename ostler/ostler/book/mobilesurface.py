"""The generic surface of a mobile app: an Android device on the app's screens. The book's surface keeps only what
is specific to its app, which is how each interaction is performed and what the rows read as."""

from __future__ import annotations

from typing import Any

from ostler.book.device import Device
from ostler.book.environment import Environment
from ostler.book.pagesurface import PageSurface


class MobileSurface(PageSurface):
    """Subclass per mobile app. `app_id` is the bundle id the app installs as. The screens and the recording are
    those of a web book, the component finders and the verbs are the device's. `self.browser` is the device, so
    a book writes the same `fill`, `press` and `wait_for` calls as on the web."""

    name = "mobile"
    app_id = ""
    timeout = 60.0

    def drive(self, environment: Environment, lang: str) -> Any:
        return Device(self.app_id, lang, timeout=self.timeout)

    def start(self) -> None:
        self.browser.start()

    def reset(self) -> None:
        self.restore()
        self.open()

    def strays(self) -> list[str]:
        return []

    def list_faults(self) -> list[str]:
        return []

    def lists_read(self) -> frozenset[str]:
        return frozenset()

    def disabled(self, component: Any, row: Any = None) -> str | None:
        return None if self.browser.disabled(component) else f"{component.found_by(self.lang)} is enabled"
