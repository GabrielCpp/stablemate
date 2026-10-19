from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.notifications import SeverityLevel
from textual.widgets import Footer, OptionList, Static

from groom.tui import dispatch
from groom.tui.clean import clean
from groom.tui.link import Frame, Link, LinkError
from groom.tui.route import route
from groom.tui.screens.confirm import Confirm
from groom.tui.screens.enqueue import EnqueueForm
from groom.tui.screens.panel import Panel
from groom.tui.widgets.options import sync_options

BASE = "/api/dispatch"
POLL_S = 5.0
CHUNK = 100


class DispatchScreen(Panel):
    DEFAULT_CSS = """
    DispatchScreen #dispatch-queues-pane { width: 28%; border-right: solid $primary-darken-2; }
    DispatchScreen #dispatch-items-pane { width: 30%; border-right: solid $primary-darken-2; }
    DispatchScreen OptionList { height: 1fr; }
    DispatchScreen .dispatch-note { height: auto; padding: 0 1; color: $text-muted; }
    DispatchScreen #dispatch-detail { width: 1fr; padding: 0 1; }
    DispatchScreen #dispatch-detail Static { height: auto; }
    """
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("n", "enqueue", "Enqueue"),
        Binding("c", "cancel_item", "Cancel item"),
        Binding("x", "stop_item", "Stop item"),
    ]

    def __init__(self, link: Link) -> None:
        super().__init__()
        self.link = link
        self.queues: list[Frame] | None = None
        self.qfail = ""
        self.items: list[Frame] | None = None
        self.ifail = ""
        self.queue = ""
        self.item = ""
        self.shown = CHUNK
        self._queue_cache: dict[str, Text] = {}
        self._item_cache: dict[str, Text] = {}

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="dispatch-queues-pane"):
                yield OptionList(id="dispatch-queues")
                yield Static(id="dispatch-queues-note", classes="dispatch-note")
            with Vertical(id="dispatch-items-pane"):
                yield OptionList(id="dispatch-items")
                yield Static(id="dispatch-items-note", classes="dispatch-note")
            with VerticalScroll(id="dispatch-detail"):
                yield Static(id="dispatch-detail-text")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dispatch-queues", OptionList).focus()
        self._show_queues()
        self._show_items()
        self.run_worker(self._load(), group="dispatch-poll", exclusive=True, exit_on_error=False)
        self.set_interval(POLL_S, self._tick)

    def _tick(self) -> None:
        self.run_worker(self._load(), group="dispatch-poll", exclusive=True, exit_on_error=False)

    async def _load(self) -> None:
        await self._fetch_queues()
        if self.queue:
            await self._fetch_items(self.queue)

    async def _fetch_queues(self) -> None:
        try:
            body = await self.link.get(f"{BASE}/queues")
        except LinkError as exc:
            self.qfail = clean(exc)
        else:
            self.qfail = ""
            self.queues = list(body.get("queues") or [])
        self._show_queues()

    async def _fetch_items(self, queue: str) -> None:
        try:
            body = await self.link.get(route(BASE, queue) + "/items")
        except LinkError as exc:
            if self.queue == queue:
                self.ifail = clean(exc)
                self._show_items()
            return
        if self.queue != queue:
            return
        self.ifail = ""
        self.items = list(body.get("items") or [])
        self._show_items()

    def _queue_row(self) -> Frame | None:
        return next((row for row in self.queues or [] if str(row.get("name")) == self.queue), None)

    def _item_row(self) -> Frame | None:
        return next((row for row in self.items or [] if str(row.get("item_id")) == self.item), None)

    def _show_queues(self) -> None:
        listing = self.query_one("#dispatch-queues", OptionList)
        rows = self.queues or []
        if self.qfail:
            note = f"Could not load queues: {self.qfail}"
        elif self.queues is None:
            note = dispatch.LOADING_TEXT
        else:
            note = "" if rows else dispatch.EMPTY_TEXT
        items = [(str(row["name"]), dispatch.queue_row(row)) for row in rows if row.get("name")]
        self._queue_cache = sync_options(listing, items, self._queue_cache, self.queue)
        self.query_one("#dispatch-queues-note", Static).update(Text(note))
        self._follow_queue()

    def _follow_queue(self) -> None:
        listing = self.query_one("#dispatch-queues", OptionList)
        if listing.highlighted is None:
            return
        name = str(listing.get_option_at_index(listing.highlighted).id)
        if name != self.queue:
            self._select_queue(name)
        self.refresh_bindings()

    def _select_queue(self, name: str) -> None:
        self.queue = name
        self.items = None
        self.ifail = ""
        self.item = ""
        self.shown = CHUNK
        self._show_items()
        self.run_worker(self._fetch_items(name), group="dispatch-items", exclusive=True, exit_on_error=False)

    def _show_items(self) -> None:
        listing = self.query_one("#dispatch-items", OptionList)
        rows = self.items or []
        if not self.queue:
            note = dispatch.NO_QUEUE_TEXT
        elif self.ifail:
            note = f"Could not load items: {self.ifail}"
        elif self.items is None:
            note = ""
        else:
            note = "" if rows else dispatch.NO_ITEMS_TEXT
        items = [(str(row["item_id"]), dispatch.item_row(row)) for row in rows[: self.shown] if row.get("item_id")]
        self._item_cache = sync_options(listing, items, self._item_cache, self.item)
        if len(rows) > self.shown:
            self.call_after_refresh(self._grow)
        self.query_one("#dispatch-items-note", Static).update(Text(note))
        self._follow_item()

    def _grow(self) -> None:
        self.shown += CHUNK
        self._show_items()

    def _follow_item(self) -> None:
        listing = self.query_one("#dispatch-items", OptionList)
        if listing.highlighted is not None:
            self.item = str(listing.get_option_at_index(listing.highlighted).id)
        self._show_detail()

    def _show_detail(self) -> None:
        row = self._item_row()
        if not self.item:
            body = Text(dispatch.NO_ITEM_TEXT, style="dim")
        elif row is None:
            body = Text(dispatch.GONE_TEXT, style="dim")
        else:
            body = dispatch.detail_text(row, self.queue)
        self.query_one("#dispatch-detail-text", Static).update(body)
        self.refresh_bindings()

    @on(OptionList.OptionHighlighted, "#dispatch-queues")
    def _queue_highlighted(self) -> None:
        self._follow_queue()

    @on(OptionList.OptionHighlighted, "#dispatch-items")
    def _item_highlighted(self) -> None:
        self._follow_item()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "enqueue":
            return self._queue_row() is not None
        if action in ("cancel_item", "stop_item"):
            row = self._item_row()
            return row is not None and row.get("status") == ("pending" if action == "cancel_item" else "running")
        return True

    def action_cursor_down(self) -> None:
        if isinstance(self.focused, OptionList):
            self.focused.action_cursor_down()

    def action_cursor_up(self) -> None:
        if isinstance(self.focused, OptionList):
            self.focused.action_cursor_up()

    def action_enqueue(self) -> None:
        row = self._queue_row()
        if row is None:
            return
        queue = self.queue
        params: list[Frame] = row.get("params") or []
        if dispatch.fields(params):
            self.app.push_screen(EnqueueForm(queue, params, lambda values: self._enqueue(queue, values)))
            return

        def decided(yes: bool | None) -> None:
            if yes:
                self.run_worker(self._enqueue(queue, {}), exit_on_error=False)

        self.app.push_screen(Confirm(f"Enqueue on {clean(queue)}?"), decided)

    def action_cancel_item(self) -> None:
        row = self._item_row()
        if row is None or row.get("status") != "pending":
            return
        queue, item_id = self.queue, str(row["item_id"])

        def decided(yes: bool | None) -> None:
            if yes:
                self.run_worker(self._cancel(queue, item_id), exit_on_error=False)

        self.app.push_screen(Confirm(f"Cancel {clean(item_id)}? It never starts."), decided)

    def action_stop_item(self) -> None:
        row = self._item_row()
        if row is None or row.get("status") != "running":
            return
        queue, item_id = self.queue, str(row["item_id"])

        def decided(yes: bool | None) -> None:
            if yes:
                self.run_worker(self._stop(queue, item_id), exit_on_error=False)

        self.app.push_screen(Confirm(f"Stop {clean(item_id)}? Its process is killed."), decided)

    def _toast(self, message: str, severity: SeverityLevel = "warning") -> None:
        self.app.notify(message, title="groom", severity=severity, markup=False)

    async def _enqueue(self, queue: str, values: dict[str, str]) -> bool:
        accepted = False
        try:
            reply = await self.link.post(route(BASE, queue) + "/items", {"params": values})
        except LinkError as exc:
            self._toast(f"groom did not accept the item: {clean(exc)}", "error")
        else:
            accepted = bool(reply.get("ok"))
            if accepted:
                item = reply.get("item") or {}
                self._toast(f"Enqueued {clean(item.get('item_id'))} on {clean(queue)}.", "information")
            else:
                reason = clean(reply.get("error")) or "no reason given"
                self._toast(f"groom did not accept the item: {reason}", "error")
        await self._load()
        return accepted

    async def _cancel(self, queue: str, item_id: str) -> None:
        try:
            reply = await self.link.delete(route(route(BASE, queue) + "/items", item_id))
        except LinkError as exc:
            self._toast(f"groom did not answer the cancel: {clean(exc)}", "error")
        else:
            if not reply.get("ok"):
                self._toast("That item was already running or done.")
        await self._load()

    async def _stop(self, queue: str, item_id: str) -> None:
        try:
            reply = await self.link.post(route(route(BASE, queue) + "/items", item_id) + "/stop")
        except LinkError as exc:
            self._toast(f"groom did not answer the stop: {clean(exc)}", "error")
        else:
            if not reply.get("ok"):
                self._toast("That item was already gone.")
        await self._load()
