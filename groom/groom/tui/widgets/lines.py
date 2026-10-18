from __future__ import annotations

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.text import Text
from textual import on
from textual.markup import escape
from textual.widgets import Button, Collapsible, Static
from textual.widgets.collapsible import CollapsibleTitle

from groom.tui.clean import clean
from groom.tui.link import Frame
from groom.tui.widgets.reconcile import Reconcilable, reconcile


ENTRY_PAGE = 40
EARLIER_KEY = "earlier"


def _prose(text: object) -> RenderableType:
    return Markdown(clean(text), hyperlinks=False)


def _title(text: str, bad: bool = False) -> str:
    shown = escape(text)
    return f"[red]{shown}[/red]" if bad else shown


class DividerEntry(Reconcilable, Static):
    def __init__(self, key: str, entry: Frame) -> None:
        Reconcilable.__init__(self, key, entry)
        Static.__init__(self, Text(clean(entry.get("label")), style="dim italic"), classes="entry-divider")


class MessageEntry(Reconcilable, Static):
    def __init__(self, key: str, entry: Frame) -> None:
        Reconcilable.__init__(self, key, entry)
        role = Text(clean(entry.get("role")) or "assistant", style="bold dim")
        Static.__init__(self, Group(role, _prose(entry.get("text"))), classes="entry-message")


class FoldedMessageEntry(Reconcilable, Collapsible):
    def __init__(self, key: str, entry: Frame) -> None:
        Reconcilable.__init__(self, key, entry)
        Collapsible.__init__(
            self,
            Static(_prose(entry.get("text"))),
            title=_title(clean(entry.get("role")) or "user"),
            collapsed=True,
            classes="entry-message",
        )


class PlainToolEntry(Reconcilable, Static):
    def __init__(self, key: str, entry: Frame) -> None:
        Reconcilable.__init__(self, key, entry)
        Static.__init__(self, _tool_head(entry), classes="entry-tool")


class ToolEntry(Reconcilable, Collapsible):
    def __init__(self, key: str, entry: Frame, body: str) -> None:
        Reconcilable.__init__(self, key, entry)
        Collapsible.__init__(
            self,
            Static(Text(body)),
            title=_title(_tool_title(entry), bool(entry.get("failed"))),
            collapsed=True,
            classes="entry-tool",
        )


def _tool_title(entry: Frame) -> str:
    return f"{clean(entry.get('name'))} {clean(entry.get('summary'))}".strip()


def _tool_head(entry: Frame) -> Text:
    return Text(_tool_title(entry), style="red" if entry.get("failed") else "")


class EarlierEntries(Reconcilable, Button):
    DEFAULT_CSS = """
    EarlierEntries { height: 1; min-width: 0; border: none; padding: 0 1; margin: 0; }
    EarlierEntries:focus { text-style: bold reverse; }
    """

    def __init__(self, key: str, entry: Frame) -> None:
        Reconcilable.__init__(self, key, entry)
        Button.__init__(self, self._label(entry), classes="entry-earlier")

    @staticmethod
    def _label(entry: Frame) -> str:
        return f"Show {entry.get('n')} earlier entries ({entry.get('hidden')} hidden)"

    async def update_data(self, data: Frame) -> bool:
        self.data = data
        self.label = self._label(data)
        return True


def tail_entries(keyed: list[tuple[str, Frame]], limit: int) -> tuple[int, list[tuple[str, Frame]]]:
    hidden = max(len(keyed) - limit, 0)
    return hidden, keyed[hidden:]


def windowed(keyed: list[tuple[str, Frame]], limit: int) -> list[tuple[str, Frame]]:
    hidden, shown = tail_entries(keyed, limit)
    if not hidden:
        return shown
    marker = {"kind": "earlier", "n": min(ENTRY_PAGE, hidden), "hidden": hidden}
    return [(EARLIER_KEY, marker), *shown]


def build_entry(key: str, entry: Frame) -> Static | Collapsible | Button:
    kind = entry.get("kind")
    if kind == "earlier":
        return EarlierEntries(key, entry)
    if kind == "divider":
        return DividerEntry(key, entry)
    if kind == "tool":
        body = "\n\n".join(clean(entry.get(name)) for name in ("detail", "result") if entry.get(name))
        return ToolEntry(key, entry, body) if body else PlainToolEntry(key, entry)
    if entry.get("collapsed"):
        return FoldedMessageEntry(key, entry)
    return MessageEntry(key, entry)


def entry_keys(entries: list[Frame]) -> list[tuple[str, Frame]]:
    return [(str(entry.get("key") or f"#{index}"), entry) for index, entry in enumerate(entries)]


class PlainLine(Reconcilable, Static):
    def __init__(self, key: str, line: Frame) -> None:
        Reconcilable.__init__(self, key, line)
        text = Text(style="red" if line.get("cls") == "bad" else "")
        text.append(clean(line.get("ts")) + " ", style="dim")
        text.append(f"{clean(line.get('level')):<5}")
        node = clean(line.get("node"))
        if node:
            text.append(node + " ", style="dim")
        text.append(clean(line.get("body")))
        Static.__init__(self, text, classes="trail-line")


class TurnGroup(Reconcilable, Collapsible):
    def __init__(self, key: str, line: Frame, opened: dict[str, bool], limits: dict[str, int]) -> None:
        Reconcilable.__init__(self, key, line)
        self.slug = clean(line.get("slug"))
        self.opened = opened
        self.limits = limits
        Collapsible.__init__(
            self,
            *(build_entry(entry_key, entry) for entry_key, entry in self._window(line)),
            title=self._heading(line),
            collapsed=not self._wants_open(line),
            classes="trail-turn",
        )

    def _window(self, line: Frame) -> list[tuple[str, Frame]]:
        return windowed(entry_keys(line.get("entries") or []), self.limits.get(self.slug, ENTRY_PAGE))

    def _wants_open(self, line: Frame) -> bool:
        return bool(self.opened.get(self.slug, line.get("status") == "running"))

    @staticmethod
    def _heading(line: Frame) -> str:
        parts = (line.get(name) for name in ("ts", "node", "slug", "status", "duration"))
        return _title(" ".join(clean(part) for part in parts if part), line.get("cls") == "bad")

    @on(CollapsibleTitle.Toggle)
    def _remember_toggle(self) -> None:
        self.call_after_refresh(self._record_choice)

    def _record_choice(self) -> None:
        self.opened[self.slug] = not self.collapsed

    @on(Button.Pressed)
    async def _show_earlier(self, event: Button.Pressed) -> None:
        if isinstance(event.button, EarlierEntries):
            event.stop()
            self.limits[self.slug] = self.limits.get(self.slug, ENTRY_PAGE) + ENTRY_PAGE
            await self._render_entries(self.data)

    async def _render_entries(self, data: Frame) -> None:
        await reconcile(self.query_one(Collapsible.Contents), self._window(data), build_entry)

    async def update_data(self, data: Frame) -> bool:
        self.data = data
        self.title = self._heading(data)
        self.collapsed = not self._wants_open(data)
        await self._render_entries(data)
        return True


def build_line(key: str, line: Frame, opened: dict[str, bool], limits: dict[str, int]) -> Static | Collapsible:
    if line.get("kind") == "turn":
        return TurnGroup(key, line, opened, limits)
    return PlainLine(key, line)


def line_keys(lines: list[Frame]) -> list[tuple[str, Frame]]:
    seen: dict[str, int] = {}
    keyed = []
    for line in lines:
        if line.get("kind") == "turn":
            key = f"turn:{line.get('key') or line.get('slug')}"
        else:
            base = f"{line.get('kind')}|{line.get('ts')}|{line.get('node')}|{line.get('body')}"
            seen[base] = seen.get(base, 0) + 1
            key = f"{base}#{seen[base]}"
        keyed.append((key, line))
    return keyed
