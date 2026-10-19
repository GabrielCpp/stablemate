from __future__ import annotations

from textual.binding import Binding
from textual.widgets import Input


class RunFilter(Input):
    BINDINGS = [Binding("escape", "dismiss", "Clear", show=False)]

    def __init__(self) -> None:
        super().__init__(placeholder="Filter runs", id="filter")
        self.display = False

    def reveal(self) -> None:
        self.display = True
        self.focus()

    def action_dismiss(self) -> None:
        self.value = ""
        self.display = False
        self.screen.query_one("#runs").focus()
