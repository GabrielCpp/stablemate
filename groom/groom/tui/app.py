from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.widgets import Button, Footer, OptionList, Static
from textual.widgets.option_list import Option

from groom.tui import store as client
from groom.tui.clean import clean
from groom.tui.connection import (
    EVAL_EVERY_S,
    RESYNC_EVERY_S,
    Connection,
    Observation,
    backoff_delay,
    derive_connection,
)
from groom.tui.link import Frame, Link, LinkError
from groom.tui.widgets.detail import DetailPane
from groom.tui.widgets.fleet import row_text, status_text
from groom.tui.widgets.gate import GateBlock

def _now_ms() -> float:
    return time.monotonic() * 1000


class GroomTui(App[None]):
    TITLE = "groom"
    CSS = """
    #status { height: 1; padding: 0 1; background: $boost; }
    #runs { width: 45%; border-right: solid $primary-darken-2; }
    #detail { width: 1fr; padding: 0 1; }
    #head { text-style: bold; }
    #note, #notice, #trail-empty, #activity, #tabs { height: auto; }
    #metrics, #trail-bar { height: auto; margin-top: 1; }
    #trail-tab, #trail-lines, #gate-tab { height: auto; }
    .trail-line { height: auto; }
    .trail-turn { height: auto; padding-left: 0; }
    .entry-message, .entry-tool, .entry-divider { height: auto; }
    .gate-path { color: $text-muted; margin-top: 1; }
    .question { margin: 0; padding: 0; }
    .answer { height: 6; }
    .send { margin-top: 1; }
    GateBlock { height: auto; }
    #gates { height: auto; }
    Collapsible { padding-bottom: 0; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("enter", "open_run", "Open"),
        Binding("g", "show_tab('gate')", "Gate"),
        Binding("t", "show_tab('trail')", "Trail"),
        Binding("d", "show_tab('diff')", "Diff"),
        Binding("f", "show_tab('files')", "Files"),
        Binding("p", "pick_repo", "Repository"),
        Binding("v", "cycle_view", "View"),
        Binding("K", "cycle_kind", "Telemetry kind"),
        Binding("a", "focus_answer", "Answer"),
        Binding("ctrl+s", "send_answer", "Send"),
        Binding("r", "refresh", "Rescan"),
        Binding("escape", "focus_runs", "Runs", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, link: Link) -> None:
        super().__init__()
        self.link = link
        self.store = client.Store()
        self.connection = Connection("reconnecting", True)
        self._open = False
        self._last_message = 0.0
        self._closed_since = _now_ms()
        self._last_resync = 0.0
        self._resync_running = False
        self._row_cache: dict[str, Text] = {}

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        with Horizontal():
            yield OptionList(id="runs")
            yield DetailPane()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#runs", OptionList).focus()
        self._render_status()
        self.run_worker(self._connection_loop(), exit_on_error=False)
        self.set_interval(EVAL_EVERY_S, self.evaluate)

    async def on_unmount(self) -> None:
        await self.link.close()

    @property
    def pane(self) -> DetailPane:
        return self.query_one(DetailPane)

    async def _connection_loop(self) -> None:
        attempt = 0
        while True:
            try:
                await self.link.open()
            except LinkError:
                self._mark_closed()
                await asyncio.sleep(backoff_delay(attempt))
                attempt += 1
                continue
            attempt = 0
            self._open = True
            self._last_message = _now_ms()
            self.evaluate()
            if self.store.selected:
                await self.link.send({"cmd": "watch", "run_id": self.store.selected})
            async for frame in self.link.frames():
                if not self.is_running:
                    return
                self._last_message = _now_ms()
                await self.handle_frame(frame)
                self.evaluate()
            self._mark_closed()
            await asyncio.sleep(backoff_delay(attempt))
            attempt += 1

    def _mark_closed(self) -> None:
        if self._open:
            self._closed_since = _now_ms()
        self._open = False
        self.evaluate()

    def evaluate(self) -> None:
        if not self.is_running:
            return
        self.connection = derive_connection(Observation(
            now=_now_ms(),
            socket_open=self._open,
            last_message_ts=self._last_message,
            closed_since=self._closed_since,
        ))
        self._render_status()
        if (
            self.connection.resyncing
            and not self._resync_running
            and _now_ms() - self._last_resync >= RESYNC_EVERY_S * 1000
        ):
            self._resync_running = True
            self.run_worker(self._resync(), exit_on_error=False)

    async def _resync(self) -> None:
        try:
            body = await self.link.get("/api/state")
        except LinkError:
            return
        finally:
            self._last_resync = _now_ms()
            self._resync_running = False
        await self.handle_frame({**body, "type": "state"})

    async def handle_frame(self, frame: Frame) -> None:
        if not self.is_running:
            return
        kind = frame.get("type")
        if kind == "state":
            self.store = client.apply_state(self.store, frame)
            self._render_fleet()
            await self._render_detail()
        elif kind == "run":
            self.store = client.apply_run(self.store, frame)
            self._render_fleet()
            if frame.get("run", {}).get("id") == self.store.selected:
                await self._render_detail()
        elif kind == "detail":
            before = self.store
            self.store = client.apply_detail(self.store, frame)
            if self.store is not before:
                await self._render_detail()
        elif kind == "notify":
            self.notify(clean(frame.get("message") or "A workflow needs your input."), title="groom: blocked", severity="warning")
            self.bell()
        elif kind == "answered":
            await self._on_answered(frame)
        elif kind == "answer_rejected":
            reason = clean(frame.get("reason")) or "groom refused it"
            self.notify(f"Answer not taken: {reason}.", title="groom", severity="error", markup=False)

    async def _on_answered(self, frame: Frame) -> None:
        path = client.answered_gate(self.store, frame)
        if not path:
            return
        for block in self.pane.blocks():
            if block.file_path == path and block.answer_box is not None:
                block.answer_box.clear()
        self.notify("Answer sent.", title="groom")

    def _render_status(self) -> None:
        self.query_one("#status", Static).update(status_text(self.connection, self.store))

    def _render_fleet(self) -> None:
        self._render_status()
        runs = self.store.runs
        listing = self.query_one("#runs", OptionList)
        ids = [str(row["id"]) for row in runs]
        current = [str(listing.get_option_at_index(i).id) for i in range(listing.option_count)]
        texts = {str(row["id"]): row_text(row) for row in runs}
        if ids == current:
            for run_id, text in texts.items():
                if self._row_cache.get(run_id) != text:
                    listing.replace_option_prompt(run_id, text)
                    self._row_cache[run_id] = text
            return
        highlighted = listing.highlighted
        keep = current[highlighted] if highlighted is not None and highlighted < len(current) else ""
        listing.clear_options()
        listing.add_options([Option(texts[run_id], id=run_id) for run_id in ids])
        self._row_cache = texts
        if ids:
            listing.highlighted = ids.index(keep) if keep in ids else 0

    async def _render_detail(self) -> None:
        await self.pane.show(self.store)

    @on(OptionList.OptionSelected, "#runs")
    async def _selected(self, event: OptionList.OptionSelected) -> None:
        if event.option.id is not None:
            await self.open_run(str(event.option.id))

    async def open_run(self, run_id: str) -> None:
        self.store = client.select(self.store, run_id)
        await self._render_detail()
        if await self.link.send({"cmd": "watch", "run_id": run_id}):
            return
        try:
            body = await self.link.get(f"/worker/{run_id}")
        except LinkError:
            return
        await self.handle_frame({"type": "detail", "id": run_id, "detail": body})

    async def action_open_run(self) -> None:
        listing = self.query_one("#runs", OptionList)
        if listing.highlighted is not None:
            option = listing.get_option_at_index(listing.highlighted)
            if option.id is not None:
                await self.open_run(str(option.id))

    def action_cursor_down(self) -> None:
        self.query_one("#runs", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#runs", OptionList).action_cursor_up()

    def action_focus_runs(self) -> None:
        self.query_one("#runs", OptionList).focus()

    async def action_show_tab(self, tab: str) -> None:
        self.pane.tab = tab
        await self._render_detail()
        self.pane.open_tab(self)

    def action_pick_repo(self) -> None:
        self.pane.pick_repo(self)

    async def action_cycle_view(self) -> None:
        if self.pane.tab == "trail":
            self.store = client.cycle_view(self.store)
            await self._render_detail()

    async def action_cycle_kind(self) -> None:
        if self.pane.tab == "trail" and self.store.trail_view != "transcript":
            self.store = client.cycle_kind(self.store)
            await self._render_detail()

    async def action_focus_answer(self) -> None:
        self.pane.tab = "gate"
        await self._render_detail()
        for block in self.pane.blocks():
            if block.answer_box is not None:
                block.answer_box.focus()
                return

    async def action_refresh(self) -> None:
        try:
            await self.link.post("/refresh")
        except LinkError as exc:
            self.notify(f"Rescan failed: {clean(exc)}", title="groom", severity="error")

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


def run(url: str) -> None:
    from groom.tui.link_ws import WsLink

    GroomTui(WsLink(url)).run()
