"""A surface is a way to reach the service: an HTTP API, a web page, a mobile
screen, a command. It performs the same steps the model does and lists the same
rows."""

from __future__ import annotations

from typing import Any, Protocol

from ostler.book.outcome import Outcome


class Surface(Protocol):
    name: str

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reset(self) -> None: ...

    def perform(self, step: Any) -> Outcome: ...

    def rows(self) -> tuple[object, ...]: ...
