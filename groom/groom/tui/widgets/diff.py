from __future__ import annotations

import asyncio

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from groom.tui.changes import DiffFile, cap_note, capped, split_diff
from groom.tui.clean import clean
from groom.tui.link import Frame, Link, LinkError
from groom.tui.route import route
from groom.tui.widgets.code import CodeView, highlight_lines
from groom.tui.widgets.repo import RepoTab

LOADING_TEXT = "Loading changes…"
NO_CHANGES_TEXT = "No changes."
SELECT_TEXT = "Select a changed file to see its diff."
LOADING_DIFF_TEXT = "Loading…"


def file_text(file: DiffFile) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(file.path + "  ")
    text.append(f"+{file.added}", style="green")
    text.append(" ")
    text.append(f"-{file.deleted}", style="red")
    return text


def build_diff(text: str) -> tuple[list[Text], int]:
    shown, total = capped(text)
    return highlight_lines(shown, "diff"), total


class DiffTab(RepoTab):
    kind = "diff"
    DEFAULT_CSS = """
    DiffTab { height: auto; }
    DiffTab OptionList { height: auto; max-height: 10; }
    DiffTab Static { height: auto; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._files: list[DiffFile] = []

    def compose_body(self) -> ComposeResult:
        yield Static(id="diff-note")
        yield OptionList(id="diff-files")
        yield Static(id="diff-view-note")
        yield CodeView(id="diff-view")
        yield Static(id="diff-cap")

    def focus_list(self) -> None:
        self.query_one("#diff-files", OptionList).focus()

    def _say(self, note: str) -> None:
        self.query_one("#diff-note", Static).update(Text(note, style="dim"))

    def _view(self, file: DiffFile | None) -> None:
        self.app.workers.cancel_group(self, "highlight")
        code = self.query_one("#diff-view", CodeView)
        code.display = False
        self.query_one("#diff-cap", Static).update("")
        note = self.query_one("#diff-view-note", Static)
        if file is None:
            note.update(Text(SELECT_TEXT if self._files else "", style="dim"))
            return
        note.update(Text(LOADING_DIFF_TEXT, style="dim"))
        self.run_worker(self._highlight(file), exclusive=True, group="highlight", exit_on_error=False)

    async def _highlight(self, file: DiffFile) -> None:
        lines, total = await asyncio.to_thread(build_diff, file.text)
        code = self.query_one("#diff-view", CodeView)
        code.set_lines(lines)
        code.display = True
        self.query_one("#diff-view-note", Static).update("")
        self.query_one("#diff-cap", Static).update(Text(cap_note(total), style="dim"))

    async def clear_body(self) -> None:
        self._files = []
        self.query_one("#diff-files", OptionList).clear_options()
        self._say("")
        self._view(None)

    async def load(self, link: Link, repo: Frame) -> None:
        await self.clear_body()
        self._say(LOADING_TEXT)
        try:
            body = await link.get(route("/diff", str(repo["container"]), repo=str(repo.get("repo") or "")))
        except LinkError as exc:
            self._say(f"Could not load the diff: {clean(exc)}")
            return
        self._files = split_diff(clean(body.get("diff")))
        self._say("" if self._files else NO_CHANGES_TEXT)
        self.query_one("#diff-files", OptionList).add_options(
            [Option(file_text(file), id=str(at)) for at, file in enumerate(self._files)]
        )
        self._view(None)

    @on(OptionList.OptionHighlighted, "#diff-files")
    def _highlighted(self, event: OptionList.OptionHighlighted) -> None:
        at = event.option_index
        self._view(self._files[at] if 0 <= at < len(self._files) else None)
