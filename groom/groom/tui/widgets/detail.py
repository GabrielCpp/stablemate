from __future__ import annotations

import asyncio

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static

from groom.tui import store as client
from groom.tui.clean import clean
from groom.tui.widgets.diff import DiffTab
from groom.tui.widgets.files import FilesTab
from groom.tui.widgets.gate import GateBlock, GateTab
from groom.tui.widgets.repo import RepoHost, RepoTab
from groom.tui.widgets.trail import TrailTab, activity_text, head_text

TABS = ("gate", "trail", "diff", "files")
TAB_LABELS = {"gate": "Gate", "trail": "Trail", "diff": "Diff", "files": "Files"}


def tabs_text(active: str) -> Text:
    text = Text()
    for name in TABS:
        label = TAB_LABELS[name]
        if name == active:
            text.append(f"[{label}]", style="bold reverse")
        else:
            text.append(f" {label} ", style="dim")
        text.append(f" ({name[0]})  ", style="dim")
    return text


class DetailPane(VerticalScroll):
    def __init__(self) -> None:
        super().__init__(id="detail")
        self._lock = asyncio.Lock()
        self._run = ""
        self.tab = ""

    def compose(self) -> ComposeResult:
        yield Static(id="head")
        yield Static(id="activity")
        yield Static(id="note")
        yield Static(id="tabs")
        yield GateTab(id="gate-tab")
        yield TrailTab()
        yield DiffTab()
        yield FilesTab()

    @property
    def gate_tab(self) -> GateTab:
        return self.query_one(GateTab)

    @property
    def trail_tab(self) -> TrailTab:
        return self.query_one(TrailTab)

    @property
    def diff_tab(self) -> DiffTab:
        return self.query_one(DiffTab)

    @property
    def files_tab(self) -> FilesTab:
        return self.query_one(FilesTab)

    def repo_tab(self) -> RepoTab | None:
        return {"diff": self.diff_tab, "files": self.files_tab}.get(self.tab)

    def open_tab(self, host: RepoHost) -> None:
        tab = self.repo_tab()
        if tab is not None and host.store.selected:
            tab.open(host)
            tab.focus_list()

    def pick_repo(self, host: RepoHost) -> None:
        tab = self.repo_tab()
        if tab is not None and host.store.selected:
            tab.pick(host)

    def blocks(self) -> list[GateBlock]:
        return self.gate_tab.blocks()

    def _apply(self, tab: str) -> None:
        self.query_one("#tabs", Static).update(tabs_text(tab) if tab else "")
        self.gate_tab.display = tab == "gate"
        self.trail_tab.display = tab == "trail"
        self.diff_tab.display = tab == "diff"
        self.files_tab.display = tab == "files"

    async def show(self, store: client.Store) -> None:
        async with self._lock:
            await self._show(store)

    async def _show(self, store: client.Store) -> None:
        head = self.query_one("#head", Static)
        note = self.query_one("#note", Static)
        row = client.run_by_id(store, store.selected)
        detail = store.detail
        if store.selected != self._run:
            self._run = store.selected
            self.tab = ""
            self._apply("")
            await self.trail_tab.forget()
            await self.diff_tab.forget()
            await self.files_tab.forget()
            await self.gate_tab.clear()
        if not store.selected or row is None:
            head.update("")
            self.query_one("#activity", Static).update("")
            note.update("Select a run and press enter to read its gates and trail.")
            self._apply("")
            return
        head.update(head_text(row, detail))
        self.query_one("#activity", Static).update(activity_text(detail))
        if detail is None:
            note.update("Loading…")
            self._apply("")
            return
        if not detail.get("found", True):
            note.update("Run not found.")
            self._apply("")
            return
        note.update("")
        wanted = detail.get("gates") or []
        self.tab = self.tab or ("gate" if wanted else "trail")
        self._apply(self.tab)
        state = clean(detail.get("state") or row.get("state"))
        node = clean(detail.get("node") or row.get("node"))
        idle = f"Nothing to answer — this run is {state}" + (f" at node {node}." if node else ".")
        await self.gate_tab.show(wanted, idle)
        await self.trail_tab.show(detail, store.trail_view, store.trail_kind)
