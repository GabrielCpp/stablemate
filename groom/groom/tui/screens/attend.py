from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, OptionList, Static

from groom.tui import attend
from groom.tui.clean import clean
from groom.tui.link import Frame, Link, LinkError
from groom.tui.route import route
from groom.tui.screens.panel import Panel
from groom.tui.widgets.lines import ENTRY_PAGE, EarlierEntries, build_entry, entry_keys, windowed
from groom.tui.widgets.reconcile import reconcile
from groom.tui.widgets.options import sync_options

SESSIONS = "/api/attend/sessions"
LOADING_DETAIL = "Loading…"


class StopConfirm(ModalScreen[bool]):
    DEFAULT_CSS = """
    StopConfirm { align: center middle; }
    StopConfirm > Vertical { width: 60; height: auto; border: round $warning; padding: 1 2; background: $surface; }
    """
    BINDINGS = [
        Binding("y", "decide(True)", "Stop it"),
        Binding("n", "decide(False)", "Keep it"),
        Binding("escape", "decide(False)", "Keep it", show=False),
    ]

    def __init__(self, workflow: str) -> None:
        super().__init__()
        self.workflow = workflow

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(Text(f"Stop the attendant on {self.workflow}? The run comes back to your terminal."))
            yield Static(Text("y stop it · n keep it", style="dim"))

    def action_decide(self, stop: bool) -> None:
        self.dismiss(stop)


class AttendScreen(Panel):
    DEFAULT_CSS = """
    AttendScreen #attend-left { width: 45%; border-right: solid $primary-darken-2; }
    AttendScreen #attend-mode { height: 1; padding: 0 1; background: $boost; }
    AttendScreen #attend-list { height: 1fr; }
    AttendScreen #attend-note { height: auto; padding: 0 1; color: $text-muted; }
    AttendScreen #attend-detail { width: 1fr; padding: 0 1; }
    AttendScreen #attend-detail Static { height: auto; }
    AttendScreen #attend-body { height: auto; }
    AttendScreen .entry-message, AttendScreen .entry-tool, AttendScreen .entry-divider { height: auto; }
    """
    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("x", "stop", "Stop attendant"),
        Binding("e", "earlier", "Earlier entries"),
    ]

    def __init__(self, link: Link, rev: float = 0.0, session_id: str = "") -> None:
        super().__init__()
        self.link = link
        self.rev = rev
        self.session = session_id
        self.rows: list[Frame] | None = None
        self.entries: list[Frame] = []
        self.limit = ENTRY_PAGE
        self.mode = ""
        self.failure = ""
        self._cache: dict[str, Text] = {}

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="attend-left"):
                yield Static(id="attend-mode")
                yield OptionList(id="attend-list")
                yield Static(id="attend-note")
            with VerticalScroll(id="attend-detail"):
                yield Static(id="attend-head")
                yield Static(id="attend-resume")
                yield Static(id="attend-attempts")
                yield Vertical(id="attend-body")
                yield Static(id="attend-empty")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#attend-list", OptionList).focus()
        self._show_list()
        self.query_one("#attend-empty", Static).update(Text(attend.NO_SELECTION_TEXT, style="dim"))
        self.run_worker(self._fetch(), exit_on_error=False)
        if self.session:
            self.run_worker(self._read(self.session, None), exit_on_error=False)

    def rev_changed(self, rev: float) -> None:
        if rev != self.rev:
            self.rev = rev
            self.run_worker(self._fetch(), exit_on_error=False)

    async def _fetch(self) -> None:
        try:
            body = await self.link.get(SESSIONS)
        except LinkError as exc:
            self.failure = clean(exc)
        else:
            self.failure = ""
            self.rows = list(body.get("sessions") or [])
            self.mode = clean(body.get("mode"))
        self._show_list()

    def _show_list(self) -> None:
        listing = self.query_one("#attend-list", OptionList)
        rows = self.rows or []
        if self.failure:
            note = f"Could not load attendances: {self.failure}"
        elif self.rows is None:
            note = attend.LOADING_TEXT
        else:
            note = "" if rows else attend.EMPTY_TEXT
        items = [(str(row["job_id"]), attend.row_text(row)) for row in rows]
        prefer = next((str(row["job_id"]) for row in rows if attend.session_of(row) == self.session), "")
        self._cache = sync_options(listing, items, self._cache, prefer)
        self.query_one("#attend-note", Static).update(Text(note))
        self.query_one("#attend-mode", Static).update(Text(f"attend mode: {self.mode}" if self.mode else ""))

    def _highlighted(self) -> Frame | None:
        listing = self.query_one("#attend-list", OptionList)
        if listing.highlighted is None or not self.rows:
            return None
        job_id = str(listing.get_option_at_index(listing.highlighted).id)
        return next((row for row in self.rows if str(row["job_id"]) == job_id), None)

    def action_cursor_down(self) -> None:
        self.query_one("#attend-list", OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#attend-list", OptionList).action_cursor_up()

    @on(OptionList.OptionSelected, "#attend-list")
    def _selected(self) -> None:
        row = self._highlighted()
        if row is not None and attend.session_of(row):
            self.run_worker(self._read(attend.session_of(row), row), exit_on_error=False)

    async def _read(self, session_id: str, row: Frame | None) -> None:
        self.session = session_id
        await self._say(LOADING_DETAIL)
        try:
            body = await self.link.get(route(SESSIONS, session_id))
        except LinkError as exc:
            if self.session == session_id:
                await self._say(f"Could not load this transcript: {clean(exc)}")
            return
        if self.session == session_id:
            await self._show_detail(body, row)

    async def _say(self, message: str) -> None:
        for name in ("head", "resume", "attempts"):
            self.query_one(f"#attend-{name}", Static).update("")
        await self.query_one("#attend-body", Vertical).remove_children()
        self.query_one("#attend-empty", Static).update(Text(message, style="dim"))

    async def _show_detail(self, body: Frame, row: Frame | None) -> None:
        record = body.get("record") or row or {}
        attempts = [str(item) for item in body.get("attempts") or []]
        await self._say("" if body.get("present") else attend.NO_TRANSCRIPT_TEXT)
        self.query_one("#attend-head", Static).update(attend.head_text(record))
        self.query_one("#attend-resume", Static).update(Text(clean(body.get("resume"))))
        self.query_one("#attend-attempts", Static).update(attend.attempts_text(attempts))
        self.entries = (body.get("entries") or []) if body.get("present") else []
        self.limit = ENTRY_PAGE
        await self._render_entries()

    async def _render_entries(self) -> None:
        await reconcile(
            self.query_one("#attend-body", Vertical), windowed(entry_keys(self.entries), self.limit), build_entry
        )

    async def action_earlier(self) -> None:
        hidden = len(self.entries) - self.limit
        if hidden > 0:
            self.limit += ENTRY_PAGE
            await self._render_entries()

    @on(Button.Pressed)
    async def _earlier_pressed(self, event: Button.Pressed) -> None:
        if isinstance(event.button, EarlierEntries):
            event.stop()
            await self.action_earlier()

    def action_stop(self) -> None:
        row = self._highlighted()
        if row is None or row.get("status") != "running":
            return

        def decided(stop: bool | None) -> None:
            if stop:
                self.run_worker(self._stop(str(row["job_id"])), exit_on_error=False)

        self.app.push_screen(StopConfirm(attend.workflow_of(row)), decided)

    async def _stop(self, job_id: str) -> None:
        try:
            reply = await self.link.post(route(SESSIONS, job_id) + "/stop")
        except LinkError as exc:
            self.app.notify(
                f"groom did not answer the stop: {clean(exc)}", title="groom", severity="error", markup=False
            )
        else:
            if not reply.get("ok"):
                self.app.notify("That attendant was already gone.", title="groom", severity="warning")
        await self._fetch()
