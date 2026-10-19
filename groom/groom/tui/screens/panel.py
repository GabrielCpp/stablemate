from __future__ import annotations

from textual.binding import Binding
from textual.screen import Screen


class Panel(Screen[None]):
    BINDINGS = [Binding("escape", "back", "Back")]

    def action_back(self) -> None:
        self.app.pop_screen()
