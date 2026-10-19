from __future__ import annotations

from typing import Any

from textual import on
from textual.app import App
from textual.screen import Screen
from textual.widgets import Button

from groom.tui import store as client
from groom.tui.link import Frame, Link
from groom.tui.widgets.detail import DetailPane
from groom.tui.widgets.gate import GateBlock


class GroomBase(App[None]):
    link: Link
    store: client.Store

    @property
    def main(self) -> Screen[Any]:
        return self.screen_stack[0]

    @property
    def pane(self) -> DetailPane:
        return self.main.query_one(DetailPane)

    async def _render_detail(self) -> None:
        await self.pane.show(self.store)

    async def on_answered(self, frame: Frame) -> None:
        path = client.answered_gate(self.store, frame)
        if not path:
            return
        for block in self.pane.blocks():
            if block.file_path == path and block.answer_box is not None:
                block.answer_box.clear()
        self.notify("Answer sent.", title="groom")

    async def action_focus_answer(self) -> None:
        self.pane.tab = "gate"
        await self._render_detail()
        for block in self.pane.blocks():
            if block.answer_box is not None:
                block.answer_box.focus()
                return

    def _focused_block(self) -> GateBlock | None:
        node: Any = self.focused
        while node is not None:
            if isinstance(node, GateBlock):
                return node
            node = node.parent
        blocks = [block for block in self.pane.blocks() if block.answer_box is not None]
        return blocks[0] if blocks else None

    async def action_send_answer(self) -> None:
        block = self._focused_block()
        if block is not None:
            await self.send_answer(block)

    @on(Button.Pressed, ".send")
    async def _send_pressed(self, event: Button.Pressed) -> None:
        parent = event.button.parent
        if isinstance(parent, GateBlock):
            await self.send_answer(parent)

    async def send_answer(self, block: GateBlock) -> None:
        box = block.answer_box
        detail = self.store.detail
        if box is None or detail is None:
            return
        if not box.text.strip():
            self.notify("Write an answer first.", title="groom", severity="warning")
            return
        sent = await self.link.send({
            "cmd": "answer",
            "workflow_id": detail["id"],
            "file_path": block.file_path,
            "answer": box.text,
        })
        if not sent:
            self.notify(
                "Not sent: no connection to groom. Your answer is still in the box.",
                title="groom", severity="error",
            )
