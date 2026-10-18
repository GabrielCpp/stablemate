from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Markdown, Static, TextArea

from groom.tui.clean import clean
from groom.tui.link import Frame

MACHINE_TEXT = "Waiting for a machine result."


class GateBlock(Vertical):
    def __init__(self, gate: Frame) -> None:
        super().__init__()
        self.file_path = str(gate.get("file_path") or "")
        self.machine = gate.get("kind") == "machine"
        self._question = clean(gate.get("question"))

    def compose(self) -> ComposeResult:
        yield Static(Text(clean(self.file_path)), classes="gate-path")
        yield Markdown(self._question, classes="question")
        if self.machine:
            yield Static(MACHINE_TEXT, classes="machine")
        else:
            yield TextArea(classes="answer")
            yield Button("Send (ctrl+s)", classes="send")

    async def update_gate(self, gate: Frame) -> None:
        question = clean(gate.get("question"))
        if question != self._question:
            self._question = question
            await self.query_one(Markdown).update(question)

    @property
    def answer_box(self) -> TextArea | None:
        boxes = self.query(TextArea)
        return boxes.first() if boxes else None


class GateTab(Vertical):
    def compose(self) -> ComposeResult:
        yield Static(id="notice")
        yield Vertical(id="gates")

    def blocks(self) -> list[GateBlock]:
        return list(self.query(GateBlock))

    def say(self, message: str) -> None:
        self.query_one("#notice", Static).update(Text(message))

    async def clear(self) -> None:
        await self.query_one("#gates", Vertical).remove_children()

    async def show(self, wanted: list[Frame], idle_message: str) -> None:
        self.say("" if wanted else idle_message)
        container = self.query_one("#gates", Vertical)
        paths = {str(gate.get("file_path") or "") for gate in wanted}
        existing = {block.file_path: block for block in container.query(GateBlock)}
        for path, block in existing.items():
            if path not in paths:
                await block.remove()
        for gate in wanted:
            path = str(gate.get("file_path") or "")
            if path in existing:
                await existing[path].update_gate(gate)
            else:
                await container.mount(GateBlock(gate))
