from __future__ import annotations

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Static, Switch

from groom.tui.clean import clean
from groom.tui.link import Frame, Link, LinkError
from groom.tui.screens.panel import Panel

ENDPOINT = "/api/settings/attend"
LOADING_TEXT = "Loading settings…"
LABEL = "Attend parked and dead runs"


class SettingsScreen(Panel):
    DEFAULT_CSS = """
    SettingsScreen #settings-panel { height: auto; padding: 1 2; }
    SettingsScreen Horizontal { height: auto; }
    SettingsScreen #settings-label { padding: 1 1; width: auto; }
    SettingsScreen #settings-note { padding: 1 2; height: auto; }
    SettingsScreen #settings-panel Static { height: auto; margin-top: 1; }
    SettingsScreen #settings-panel Horizontal Static { margin-top: 0; }
    """

    def __init__(self, link: Link) -> None:
        super().__init__()
        self.link = link
        self.value: Frame | None = None
        self.saving = False

    def compose(self) -> ComposeResult:
        yield Static(Text(LOADING_TEXT, style="dim"), id="settings-note")
        with Vertical(id="settings-panel"):
            with Horizontal():
                yield Switch(id="settings-switch")
                yield Static(LABEL, id="settings-label")
            yield Static(id="settings-mode")
            yield Static(id="settings-why")
            yield Static(id="settings-source")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#settings-panel").display = False
        self.run_worker(self._load(), exit_on_error=False)

    async def _load(self) -> None:
        try:
            self.value = await self.link.get(ENDPOINT)
        except LinkError as exc:
            self.query_one("#settings-note", Static).update(Text(f"Could not load settings: {clean(exc)}"))
            return
        self.query_one("#settings-note", Static).update("")
        self.query_one("#settings-panel").display = True
        self._show()
        self.query_one(Switch).focus()

    def _show(self) -> None:
        value = self.value or {}
        mode = clean(value.get("mode"))
        switch = self.query_one(Switch)
        if not self.saving:
            with self.prevent(Switch.Changed):
                switch.value = mode != "off"
        switch.disabled = self.saving
        self.query_one("#settings-mode", Static).update(Text(mode + (" · saving…" if self.saving else "")))
        cli = clean(value.get("cli"))
        self.query_one("#settings-why", Static).update(Text(
            f"headless mode spawns {cli} and owns the process. "
            "session mode only publishes the job for a terminal you already have open. "
            "Turning this off leaves every stopped run for you."
        ))
        source = clean((value.get("sources") or {}).get("mode")) or "default"
        extra = ". The config is not carrying this key." if source == "environment" else ""
        self.query_one("#settings-source", Static).update(Text(f"value from {source}{extra}", style="dim"))

    @on(Switch.Changed)
    def _toggled(self, event: Switch.Changed) -> None:
        event.stop()
        self.run_worker(self._save(event.value), exit_on_error=False)

    async def _save(self, enabled: bool) -> None:
        self.saving = True
        self._show()
        try:
            self.value = await self.link.post(ENDPOINT, {"enabled": enabled})
        except LinkError as exc:
            self.app.notify(
                f"groom did not accept the setting: {clean(exc)}", title="groom", severity="error", markup=False
            )
        self.saving = False
        self._show()
        self.query_one(Switch).focus()
