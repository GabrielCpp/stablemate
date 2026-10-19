from __future__ import annotations

from typing import Protocol

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from groom.tui import store as client
from groom.tui.changes import default_repo, repo_items
from groom.tui.clean import clean
from groom.tui.link import Frame, Link, LinkError

LOADING_TEXT = "Loading…"
NO_REPOS_TEXT = "No repositories available."
STATE_STYLE = {"blocked": "bold yellow", "running": "green", "idle": "cyan", "finished": "dim"}


class RepoHost(Protocol):
    link: Link
    store: client.Store


def item_text(item: Frame) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    state = clean(item.get("state"))
    text.append(f"{state:<9}", style=STATE_STYLE.get(state, "dim"))
    text.append(f"{clean(item.get('type')):<9}", style="dim")
    text.append(clean(item.get("label")))
    return text


class RepoPicker(ModalScreen["Frame | None"]):
    DEFAULT_CSS = """
    RepoPicker { align: center middle; }
    RepoPicker > Vertical { width: 70%; height: auto; max-height: 80%; border: round $primary; padding: 0 1; background: $surface; }
    RepoPicker OptionList { height: auto; max-height: 16; }
    """
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "move(1)", "Down", show=False),
        Binding("up", "move(-1)", "Up", show=False),
    ]

    def __init__(self, link: Link) -> None:
        super().__init__()
        self.link = link
        self._groups: list[Frame] = []
        self._items: list[Frame] = []
        self._loaded = False
        self._failure = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Filter repositories", id="repo-filter")
            yield OptionList(id="repo-options")
            yield Static(LOADING_TEXT, id="repo-note")

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        self.run_worker(self._load(), exit_on_error=False)

    async def _load(self) -> None:
        try:
            self._groups = await self.link.get_list("/repos")
        except LinkError as exc:
            self._failure = clean(exc)
        self._loaded = True
        self._refill()

    def _refill(self) -> None:
        listing = self.query_one(OptionList)
        listing.clear_options()
        self._items = repo_items(self._groups, self.query_one(Input).value)
        listing.add_options([Option(item_text(item), id=str(at)) for at, item in enumerate(self._items)])
        note = ""
        if not self._loaded:
            note = LOADING_TEXT
        elif self._failure:
            note = f"Could not load repositories: {self._failure}"
        elif not self._items:
            note = NO_REPOS_TEXT
        self.query_one("#repo-note", Static).update(Text(note, style="dim"))
        if self._items:
            listing.highlighted = 0

    @on(Input.Changed)
    def _filtered(self) -> None:
        self._refill()

    @on(Input.Submitted)
    def _submitted(self) -> None:
        listing = self.query_one(OptionList)
        if listing.highlighted is not None and listing.highlighted < len(self._items):
            self.dismiss(self._items[listing.highlighted])

    @on(OptionList.OptionSelected)
    def _clicked(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(self._items[event.option_index])

    def action_move(self, delta: int) -> None:
        listing = self.query_one(OptionList)
        if self._items:
            at = listing.highlighted or 0
            listing.highlighted = max(0, min(len(self._items) - 1, at + delta))

    def action_cancel(self) -> None:
        self.dismiss(None)


class RepoTab(Vertical):
    kind = ""

    def __init__(self) -> None:
        super().__init__(id=f"{self.kind}-tab")

    def compose(self) -> ComposeResult:
        yield Static(id=f"{self.kind}-repo")
        yield from self.compose_body()

    def compose_body(self) -> ComposeResult:
        yield from ()

    def focus_list(self) -> None:
        raise NotImplementedError

    async def clear_body(self) -> None:
        raise NotImplementedError

    async def load(self, link: Link, repo: Frame) -> None:
        raise NotImplementedError

    async def forget(self) -> None:
        self.app.workers.cancel_group(self, self.kind)
        self.query_one(f"#{self.kind}-repo", Static).update("")
        await self.clear_body()

    def open(self, host: RepoHost) -> None:
        self.run_worker(self._open(host), exclusive=True, group=self.kind, exit_on_error=False)

    def pick(self, host: RepoHost) -> None:
        async def chosen(item: Frame | None) -> None:
            if item is not None:
                host.store = client.choose_repo(host.store, item)
                self.open(host)

        self.app.push_screen(RepoPicker(host.link), chosen)

    async def _open(self, host: RepoHost) -> None:
        repo = host.store.repo
        if repo is None:
            try:
                groups = await host.link.get_list("/repos")
            except LinkError:
                groups = []
            row = client.run_by_id(host.store, host.store.selected)
            repo = default_repo(groups, host.store.selected, str(row["name"]) if row else "")
            host.store = client.choose_repo(host.store, repo)
        label = clean(repo.get("label"))
        self.query_one(f"#{self.kind}-repo", Static).update(Text(f"Repository: {label}  (p to change)", style="dim"))
        await self.load(host.link, repo)
