from __future__ import annotations

import asyncio
import time
from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Input, OptionList, Static

from groom.tui import store as client
from groom.tui.base import GroomBase
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
from groom.tui.screens.attend import AttendScreen
from groom.tui.screens.dispatch import DispatchScreen
from groom.tui.screens.panel import Panel
from groom.tui.screens.settings import SettingsScreen
from groom.tui.styles import CSS
from groom.tui.widgets.detail import DetailPane
from groom.tui.widgets.fleet import NO_MATCH_TEXT, row_text, status_text
from groom.tui.widgets.options import sync_options
from groom.tui.widgets.palette import FleetProvider
from groom.tui.widgets.runfilter import RunFilter

def _now_ms() -> float:
    return time.monotonic() * 1000


class GroomTui(GroomBase):
    TITLE = "groom"
    CSS = CSS
    COMMANDS = GroomBase.COMMANDS | {FleetProvider}
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("enter", "open_run", "Open"),
        Binding("slash", "filter", "Filter"),
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
        Binding("A", "goto('attend')", "Attendant"),
        Binding("D", "goto('dispatch')", "Dispatch"),
        Binding("S", "goto('settings')", "Settings"),
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
            with Vertical(id="left"):
                yield RunFilter()
                yield OptionList(id="runs")
                yield Static(id="runs-note")
            yield DetailPane()
        yield Footer()

    def on_mount(self) -> None:
        self.main.query_one("#runs", OptionList).focus()
        self._render_status()
        self.run_worker(self._connection_loop(), exit_on_error=False)
        self.set_interval(EVAL_EVERY_S, self.evaluate)

    async def on_unmount(self) -> None:
        await self.link.close()

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
            self._follow_attend()
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
            await self.on_answered(frame)
        elif kind == "answer_rejected":
            reason = clean(frame.get("reason")) or "groom refused it"
            self.notify(f"Answer not taken: {reason}.", title="groom", severity="error", markup=False)

    def _follow_attend(self) -> None:
        rev = float(self.store.attend.get("rev") or 0.0)
        for screen in self.screen_stack:
            if isinstance(screen, AttendScreen):
                screen.rev_changed(rev)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        return self.screen is self.main or action in ("goto", "quit")

    def _panel(self, name: str) -> Panel:
        if name == "settings":
            return SettingsScreen(self.link)
        if name == "dispatch":
            return DispatchScreen(self.link)
        entry = client.selected_attendant(self.store) if self.screen is self.main else None
        return AttendScreen(
            self.link, float(self.store.attend.get("rev") or 0.0), str((entry or {}).get("session_id") or "")
        )

    def action_goto(self, name: str) -> None:
        current = self.screen
        wanted = {"settings": SettingsScreen, "dispatch": DispatchScreen}.get(name, AttendScreen)
        if isinstance(current, wanted) or (current is not self.main and not isinstance(current, Panel)):
            return
        if current is self.main:
            self.push_screen(self._panel(name))
        else:
            self.switch_screen(self._panel(name))

    def _render_status(self) -> None:
        self.main.query_one("#status", Static).update(status_text(self.connection, self.store))

    def _render_fleet(self) -> None:
        self._render_status()
        runs = client.filter_runs(self.store.runs, self.store.query)
        self._show_note(runs)
        listing = self.main.query_one("#runs", OptionList)
        self._row_cache = sync_options(listing, [(str(row["id"]), row_text(row)) for row in runs], self._row_cache)

    def _show_note(self, shown: tuple[Frame, ...]) -> None:
        query = self.store.query.strip()
        note = NO_MATCH_TEXT.format(query=clean(query)) if query and not shown else ""
        self.main.query_one("#runs-note", Static).update(Text(note))

    @on(Input.Changed, "#filter")
    def _filter_changed(self, event: Input.Changed) -> None:
        self.store = client.set_query(self.store, event.value)
        self._render_fleet()

    @on(Input.Submitted, "#filter")
    def _filter_submitted(self) -> None:
        listing = self.main.query_one("#runs", OptionList)
        listing.focus()
        if listing.option_count:
            listing.highlighted = 0

    def action_filter(self) -> None:
        self.main.query_one(RunFilter).reveal()

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
        listing = self.main.query_one("#runs", OptionList)
        if listing.highlighted is not None:
            option = listing.get_option_at_index(listing.highlighted)
            if option.id is not None:
                await self.open_run(str(option.id))

    def action_cursor_down(self) -> None:
        self.main.query_one("#runs", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.main.query_one("#runs", OptionList).action_cursor_up()

    def action_focus_runs(self) -> None:
        self.main.query_one("#runs", OptionList).focus()

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

    async def action_refresh(self) -> None:
        try:
            await self.link.post("/refresh")
        except LinkError as exc:
            self.notify(f"Rescan failed: {clean(exc)}", title="groom", severity="error")


def run(url: str) -> None:
    from groom.tui.link_ws import WsLink

    GroomTui(WsLink(url)).run()
