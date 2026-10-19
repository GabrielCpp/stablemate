from __future__ import annotations

from functools import partial
from typing import Protocol, cast

from rich.text import Text
from textual.command import DiscoveryHit, Hit, Hits, Provider

from groom.tui import store as client
from groom.tui.clean import clean
from groom.tui.link import Frame

STATE_STYLE = {"blocked": "bold yellow", "running": "green", "idle": "cyan", "finished": "dim"}
TABS = (("gate", "Gate"), ("trail", "Trail"), ("diff", "Diff"), ("files", "Files"))


class FleetHost(Protocol):
    store: client.Store

    async def open_run(self, run_id: str) -> None: ...
    async def action_show_tab(self, tab: str) -> None: ...
    async def action_refresh(self) -> None: ...


def clean_row(row: Frame) -> Frame:
    return {name: clean(value) if isinstance(value, str) else value for name, value in row.items()}


def hint(row: Frame) -> str:
    return "gate" if row.get("state") == "blocked" else str(row.get("live") or row.get("state") or "")


def hit_text(row: Frame) -> Text:
    word = str(row.get("state") or "")
    parts = (row.get("repo"), "#" + str(row.get("row_id") or ""), row.get("doing"))
    shown = " ".join(str(part) for part in parts if part)
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(f"{word:<9}", style=STATE_STYLE.get(word, "dim"))
    text.append(shown)
    return text


class FleetProvider(Provider):
    @property
    def host(self) -> FleetHost:
        return cast(FleetHost, self.app)

    def commands(self) -> list[tuple[str, str, partial]]:
        host = self.host
        listed = [(f"Show {label} tab", "open the tab", partial(host.action_show_tab, tab)) for tab, label in TABS]
        return [*listed, ("Rescan", "rescan the fleet", partial(host.action_refresh))]

    async def discover(self) -> Hits:
        for raw in self.host.store.runs:
            row = clean_row(raw)
            text = hit_text(row)
            yield DiscoveryHit(text, partial(self.host.open_run, str(raw["id"])), text.plain, hint(row))
        for name, helper, command in self.commands():
            yield DiscoveryHit(name, command, name, helper)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query.strip())
        for raw in client.filter_runs(self.host.store.runs, query):
            row = clean_row(raw)
            text = hit_text(row)
            score = matcher.match(client.row_haystack(row)) or 0.01
            yield Hit(score, text, partial(self.host.open_run, str(raw["id"])), text.plain, hint(row))
        for name, helper, command in self.commands():
            if score := matcher.match(name):
                yield Hit(score, matcher.highlight(name), command, name, helper)
