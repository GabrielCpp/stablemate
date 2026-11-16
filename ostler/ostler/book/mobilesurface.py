"""The generic surface of a mobile app: an Android device on the app's screens. The book's surface keeps only what
is specific to its app, which is how each interaction is performed and what the rows read as."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ostler.book.device import Device
from ostler.book.environment import Environment
from ostler.book.errors import BookError
from ostler.book.pagesurface import PageSurface
from ostler.book.proxy import Proxy, Recording


class MobileSurface(PageSurface):
    """Subclass per mobile app. `app_id` is the bundle id the app installs as. The screens and the recording are
    those of a web book, the component finders and the verbs are the device's. `self.browser` is the device, so
    a book writes the same `fill`, `press` and `wait_for` calls as on the web.

    `listens` maps each host port the app sends its requests to onto the environment host the requests are for, as
    `{19080: "api"}`. The surface holds a recording proxy on each such port while it runs, so a list stated with
    `request(...)` reads the app's own call and the answer it got."""

    name = "mobile"
    app_id = ""
    timeout = 60.0
    listens: dict[int, str] = {}

    def drive(self, environment: Environment, lang: str) -> Any:
        self.environment = environment
        self.proxies: list[Proxy] = []
        return Device(self.app_id, lang, timeout=self.timeout)

    def start(self) -> None:
        self.browser.feeding(self.screens)
        recording = Recording()
        for port, host in self.listens.items():
            target = urlsplit(self.environment.address(host))
            if target.hostname is None or target.port is None:
                raise BookError(f"the host {host!r} stands at {target.geturl()!r}, which has no host and port to forward {port} to")
            try:
                self.proxies.append(Proxy(port, (target.hostname, target.port), recording).start())
            except BookError:
                self.release()
                raise
        self.browser.recording = recording if self.proxies else None
        self.browser.start()

    def release(self) -> None:
        for proxy in self.proxies:
            proxy.stop()
        self.proxies = []
        self.browser.recording = None

    def stop(self) -> None:
        try:
            self.browser.stop()
        finally:
            self.release()

    def stepping(self) -> None:
        self.browser.stepping()

    def reset(self) -> None:
        self.restore()
        self.open()

    def strays(self) -> list[str]:
        return []

    def disabled(self, component: Any, row: Any = None) -> str | None:
        return None if self.browser.disabled(component) else f"{component.found_by(self.lang)} is enabled"
