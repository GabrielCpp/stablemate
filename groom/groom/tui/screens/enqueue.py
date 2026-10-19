from __future__ import annotations

from collections.abc import Awaitable, Callable

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Select, Static

from groom.tui.dispatch import Field, fields, label_text, missing
from groom.tui.link import Frame

Send = Callable[[dict[str, str]], Awaitable[bool]]


class EnqueueForm(ModalScreen[None]):
    DEFAULT_CSS = """
    EnqueueForm { align: center middle; }
    EnqueueForm > Vertical { width: 70; height: auto; max-height: 90%; border: round $primary; padding: 1 2; background: $surface; }
    EnqueueForm VerticalScroll { height: auto; max-height: 24; }
    EnqueueForm .enqueue-label { height: auto; margin-top: 1; }
    EnqueueForm Horizontal { height: auto; margin-top: 1; }
    EnqueueForm Button { margin-right: 2; }
    """
    BINDINGS = [
        Binding("ctrl+s", "submit", "Enqueue"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, queue: str, params: list[Frame], send: Send) -> None:
        super().__init__()
        self.queue = queue
        self.form: list[Field] = fields(params)
        self.send = send
        self.sending = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(Text(f"Enqueue on {self.queue}", style="bold"))
            with VerticalScroll():
                for index, field in enumerate(self.form):
                    yield Static(Text(label_text(field)), classes="enqueue-label")
                    yield self._control(index, field)
            with Horizontal():
                yield Button("Enqueue", id="enqueue-send", variant="primary")
                yield Button("Cancel", id="enqueue-cancel")
            yield Static(Text("ctrl+s enqueue · escape cancel", style="dim"))

    def _control(self, index: int, field: Field) -> Input | Select[str]:
        if not field.select:
            return Input(value=field.default, id=f"enqueue-{index}")
        options = [(Text(option), option) for option in field.options]
        if field.default in field.options:
            return Select(options, allow_blank=False, value=field.default, id=f"enqueue-{index}")
        return Select(options, prompt="select…", id=f"enqueue-{index}")

    def on_mount(self) -> None:
        if self.form:
            self.query_one("#enqueue-0").focus()

    def _values(self) -> dict[str, str]:
        values = {}
        for index, field in enumerate(self.form):
            control = self.query_one(f"#enqueue-{index}")
            value = control.value if isinstance(control, Input | Select) else ""
            values[field.name] = value if isinstance(value, str) else ""
        return values

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_submit(self) -> None:
        if self.sending:
            return
        values = self._values()
        empty = missing(self.form, values)
        if empty is not None:
            self.app.notify(f"{empty.label} is required.", title="groom", severity="warning", markup=False)
            self.query_one(f"#enqueue-{self.form.index(empty)}").focus()
            return
        self.sending = True
        self.run_worker(self._send(values), exit_on_error=False)

    async def _send(self, values: dict[str, str]) -> None:
        accepted = await self.send(values)
        self.sending = False
        if accepted and self.is_attached:
            self.dismiss(None)

    @on(Input.Submitted)
    def _submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_submit()

    @on(Button.Pressed, "#enqueue-send")
    def _send_pressed(self) -> None:
        self.action_submit()

    @on(Button.Pressed, "#enqueue-cancel")
    def _cancel_pressed(self) -> None:
        self.action_cancel()
