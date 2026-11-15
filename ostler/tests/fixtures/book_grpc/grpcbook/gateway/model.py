"""The gateway keeps no record, so its model has no state and no action."""

from __future__ import annotations

from ostler.book import State


class Gatewaying(State):
    def rows(self) -> tuple[object, ...]:
        return ()
