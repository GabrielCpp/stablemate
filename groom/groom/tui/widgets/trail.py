from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from groom.tui import store as client
from groom.tui.clean import clean
from groom.tui.link import Frame
from groom.tui.widgets.lines import build_line, line_keys
from groom.tui.widgets.reconcile import reconcile

NO_TELEMETRY_TEXT = "No telemetry for this run — it is either pre-OTel or exporting to another collector."
NO_HISTORY_TEXT = "No telemetry history has been received for this run yet."
NO_MATCH_TEXT = "No records of this type in the recent history."
LIVE_STYLE = {"live": "green", "dead": "red", "done": "dim", "unknown": "dim"}


def head_text(row: Frame, detail: Frame | None) -> Text:
    header = Text(clean(row.get("name")), style="bold")
    head = (detail or {}).get("head")
    if not head:
        header.append(f"  {clean((detail or {}).get('state') or row.get('state'))}")
        node = clean((detail or {}).get("node") or row.get("node"))
        if node:
            header.append(f"  at {node}")
        return header
    header.append("  " + clean(head.get("state")))
    for prefix, name in (("node ", "node"), ("", "cli"), ("pid ", "pid")):
        if head.get(name):
            header.append("  " + prefix + clean(head[name]), style="dim" if name == "cli" else "")
    header.append("  " + clean(head.get("handle")), style="dim")
    if head.get("live_label"):
        header.append("  " + clean(head["live_label"]), style=LIVE_STYLE.get(str(head.get("live")), ""))
    if head.get("exit_hint"):
        header.append("  " + clean(head["exit_hint"]), style="green" if head.get("exit_ok") else "red")
    return header


def activity_text(detail: Frame | None) -> Text:
    head = (detail or {}).get("head") or {}
    return Text(clean(head.get("activity")), style="dim")


def metrics_text(metrics: Frame) -> Text:
    if metrics.get("empty"):
        return Text(NO_TELEMETRY_TEXT, style="dim")
    text = Text()
    for cell in metrics.get("cells") or []:
        if text:
            text.append("   ")
        text.append(clean(cell.get("key")) + " ", style="dim")
        text.append(clean(cell.get("value")), style="bold red" if cell.get("cls") == "bad" else "bold")
    alerts = metrics.get("alerts") or []
    run_dir = clean(metrics.get("run_dir"))
    if alerts or run_dir:
        text.append("\n")
        for rule in alerts:
            text.append(f" {clean(rule)} ", style="bold black on yellow")
            text.append(" ")
        if run_dir:
            text.append(run_dir, style="dim")
    return text


def bar_text(view: str, kind: str) -> Text:
    text = Text("View: ")
    for name in client.TRAIL_VIEWS:
        label = client.VIEW_LABELS[name]
        if name == view:
            text.append(f"[{label}]", style="bold reverse")
        else:
            text.append(f" {label} ", style="dim")
    text.append(" (v)")
    if view != "transcript":
        text.append(f"   Show: {client.KIND_LABELS.get(kind, kind)} (K)")
    return text


class TrailTab(Vertical):
    def __init__(self) -> None:
        super().__init__(id="trail-tab")
        self.opened: dict[str, bool] = {}
        self._shown: list[Frame] | None = None
        self._metrics: Frame | None = None
        self._bar: tuple[str, str] | None = None

    def compose(self) -> ComposeResult:
        yield Static(id="metrics")
        yield Static(id="trail-bar")
        yield Static(id="trail-empty")
        yield Vertical(id="trail-lines")

    def lines(self) -> list[Static]:
        return [child for child in self.query_one("#trail-lines", Vertical).children if isinstance(child, Static)]

    async def forget(self) -> None:
        self.opened.clear()
        self._shown = None
        self._metrics = None
        self._bar = None
        self.query_one("#metrics", Static).update("")
        self.query_one("#trail-empty", Static).update("")
        await self.query_one("#trail-lines", Vertical).remove_children()

    async def show(self, detail: Frame, view: str, kind: str) -> None:
        metrics = detail.get("metrics") or {"empty": True}
        if metrics != self._metrics:
            self._metrics = metrics
            self.query_one("#metrics", Static).update(metrics_text(metrics))
        if self._bar != (view, kind):
            self._bar = (view, kind)
            self.query_one("#trail-bar", Static).update(bar_text(view, kind))
        history = detail.get("history") or []
        shown = client.trail_lines(history, view, kind)
        if shown == self._shown:
            return
        self._shown = shown
        empty = ""
        if not shown:
            empty = NO_MATCH_TEXT if history else NO_HISTORY_TEXT
        self.query_one("#trail-empty", Static).update(Text(empty, style="dim"))
        await reconcile(
            self.query_one("#trail-lines", Vertical),
            line_keys(shown),
            lambda key, line: build_line(key, line, self.opened),
        )
