from __future__ import annotations

import asyncio

from rich.syntax import Syntax
from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode

from groom.tui.changes import PathNode, cap_note, capped, path_tree
from groom.tui.clean import clean
from groom.tui.link import Frame, Link, LinkError
from groom.tui.route import route
from groom.tui.widgets.code import CodeView, highlight_lines
from groom.tui.widgets.repo import RepoTab

LOADING_TEXT = "Loading files…"
NO_FILES_TEXT = "No files."
SELECT_TEXT = "Select a file to view it."
LOADING_FILE_TEXT = "Loading…"
EMPTY_FILE_TEXT = "Empty or binary file."


def lexer_for(lang: str, path: str, content: str) -> str:
    if lang and Syntax(content[:1], lang).lexer is not None:
        return lang
    return Syntax.guess_lexer(path, content)


def build_file(content: str, lang: str, path: str) -> tuple[list[Text], int]:
    shown, total = capped(content)
    return highlight_lines(shown, lexer_for(lang, path, shown)), total


def grow(parent: TreeNode[str], nodes: list[PathNode]) -> None:
    for node in nodes:
        label = Text(clean(node.name))
        if node.is_file:
            parent.add_leaf(label, data=node.path)
        else:
            grow(parent.add(label), node.children)


class FilesTab(RepoTab):
    kind = "files"
    DEFAULT_CSS = """
    FilesTab { height: auto; }
    FilesTab Tree { height: auto; max-height: 12; }
    FilesTab Static { height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._repo: Frame | None = None
        self._link: Link | None = None

    def compose_body(self) -> ComposeResult:
        yield Static(id="files-note")
        yield Tree("files", id="files-tree")
        yield Static(id="file-head")
        yield Static(id="file-note")
        yield CodeView(id="file-view")
        yield Static(id="file-cap")

    @property
    def file_tree(self) -> Tree[str]:
        return self.query_one("#files-tree", Tree)

    def focus_list(self) -> None:
        self.file_tree.focus()

    def _say(self, note: str) -> None:
        self.query_one("#files-note", Static).update(Text(note, style="dim"))

    def _show(self, head: str, note: str = "", lines: list[Text] | None = None, cap: str = "") -> None:
        self.query_one("#file-head", Static).update(Text(clean(head), style="bold"))
        self.query_one("#file-note", Static).update(Text(note, style="dim"))
        code = self.query_one("#file-view", CodeView)
        code.display = lines is not None
        if lines is not None:
            code.set_lines(lines)
        self.query_one("#file-cap", Static).update(Text(cap, style="dim"))

    async def clear_body(self) -> None:
        self.app.workers.cancel_group(self, "file")
        self._repo = None
        self.file_tree.clear()
        self.file_tree.show_root = False
        self._say("")
        self._show("")

    async def load(self, link: Link, repo: Frame) -> None:
        await self.clear_body()
        self._repo = repo
        self._link = link
        self._say(LOADING_TEXT)
        try:
            body = await link.get(route("/files", str(repo["container"]), repo=str(repo.get("repo") or "")))
        except LinkError as exc:
            self._say(f"Could not load files: {clean(exc)}")
            return
        paths = [str(path) for path in body.get("paths") or []]
        self._say("" if paths else NO_FILES_TEXT)
        grow(self.file_tree.root, path_tree(paths))
        self.file_tree.root.expand()
        self._show("", SELECT_TEXT if paths else "")

    @on(Tree.NodeSelected)
    def _selected(self, event: Tree.NodeSelected[str]) -> None:
        path = event.node.data
        if path is None or self._repo is None or self._link is None:
            return
        self._show(path, LOADING_FILE_TEXT)
        self.run_worker(self._fetch(self._link, self._repo, path), exclusive=True, group="file", exit_on_error=False)

    async def _fetch(self, link: Link, repo: Frame, path: str) -> None:
        try:
            body = await link.get(
                route("/file", str(repo["container"]), repo=str(repo.get("repo") or ""), path=path)
            )
        except LinkError as exc:
            self._show(path, f"Could not load the file: {clean(exc)}")
            return
        content = clean(body.get("content"))
        if not content:
            self._show(path, EMPTY_FILE_TEXT)
            return
        lines, total = await asyncio.to_thread(build_file, content, str(body.get("lang") or ""), path)
        self._show(path, lines=lines, cap=cap_note(total))
