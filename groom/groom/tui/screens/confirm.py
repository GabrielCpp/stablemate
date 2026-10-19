from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class Confirm(ModalScreen[bool]):
    DEFAULT_CSS = """
    Confirm { align: center middle; }
    Confirm > Vertical { width: 60; height: auto; border: round $warning; padding: 1 2; background: $surface; }
    """
    BINDINGS = [
        Binding("y", "decide(True)", "Yes"),
        Binding("n", "decide(False)", "No"),
        Binding("escape", "decide(False)", "No", show=False),
    ]

    def __init__(self, question: str) -> None:
        super().__init__()
        self.question = question

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(Text(self.question))
            yield Static(Text("y yes · n no", style="dim"))

    def action_decide(self, yes: bool) -> None:
        self.dismiss(yes)
