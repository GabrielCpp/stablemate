"""The dashboard in a browser. Pushes reach groom the way a workflow sends them, over HTTP,
and the page is read for what it shows."""

from __future__ import annotations

import json
import secrets
import urllib.request
from typing import Any

from ostler.book import Browser, Done, Environment, PageSurface, Refusal, answer
from ostler.book.screen import Interaction

from ..fixtures import Push, Query, Reply, Settings
from ..model.actions import handle
from ..model.records import Ack, Line, Panel
from .interactions import (
    AnswerTheGate, FilterTheList, OpenAttendant, OpenDispatch, OpenHistory, OpenRun, OpenRuns, OpenSettings, ReportExit,
    ReportGate, ReportProgress, SwitchTheAttendant,
)
from .screens import ALL as SCREENS
from .screens import Attendant, Dispatch, History, RunDetail, Runs
from .screens import Settings as SettingsScreen

HOOK = """
(() => {
  const Native = window.WebSocket;
  function Hooked(url, protocols) {
    const ws = protocols === undefined ? new Native(url) : new Native(url, protocols);
    ws.addEventListener("message", (event) => {
      try {
        const body = JSON.parse(event.data);
        if (body && Array.isArray(body.runs)) window.__shell = body;
      } catch (e) {}
    });
    return ws;
  }
  Hooked.prototype = Native.prototype;
  for (const k of ["CONNECTING", "OPEN", "CLOSING", "CLOSED"]) Hooked[k] = Native[k];
  window.WebSocket = Hooked;
})();
"""

SHELL_KEYS = ("state", "doing", "repo", "row_id", "live", "live_label")

SHOWS = """
([id, want, keys]) => {
  const shell = window.__shell;
  if (!shell) return false;
  const got = (shell.runs || []).find((r) => r.id === id);
  if (!want) return !got;
  if (!got) return false;
  return keys.every((k) => got[k] === want[k]);
}
"""

SETTLED = "() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(() => done(true))))"

READ = """
() => {
  const rows = [...document.querySelectorAll('#runs-list button.row')].map((b) => ({
    id: b.dataset.workerId,
    state: b.dataset.state,
    live: b.dataset.live,
    repo: (b.querySelector('.repo-branch') || {}).textContent || '',
    wid: (b.querySelector('.wid') || {}).textContent || '',
    label: (b.querySelector('.pulse') || {}).textContent || '',
    doing: (b.querySelector('.doing') || {}).textContent || '',
  }));
  const mode = document.querySelector('#setting-attend .setting-mode');
  return { rows, mode: mode ? mode.textContent : '' };
}
"""

PUSHES = {ReportProgress: "progress", ReportGate: "blocked", ReportExit: "exited"}
FIELDS = ("name", "repo_name", "repo_branch", "current_node", "file_path", "question", "exit_code")


class GroomDashboard(PageSurface):
    def __init__(self, environment: Environment):
        super().__init__(environment, SCREENS)
        self.base = environment.address(self.host)
        self.app_ids: dict[str, str] = {}
        self.model_ids: dict[str, str] = {}
        self.hooked: object = None

    def drive(self, environment: Environment, lang: str) -> Browser:
        return Browser(environment.address(self.host), lang, selector="{id}")

    def restore(self) -> None:
        self.app_ids.clear()
        self.model_ids.clear()
        self.post("/api/settings/attend", {"enabled": False})

    def open(self) -> None:
        if self.hooked is not self.browser.context:
            self.browser.context.add_init_script(HOOK)
            self.hooked = self.browser.context
        self.browser.open(Runs.route)
        self.browser.wait_for(Runs.root)
        self.browser.page.wait_for_function("() => Boolean(window.__shell)")
        self.browser.press(Runs.settings)
        self.browser.wait_for(SettingsScreen.mode, "attached")
        self.browser.press(SettingsScreen.runs)
        self.settle()

    def settle(self) -> None:
        self.browser.page.evaluate(SETTLED)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        with urllib.request.urlopen(request) as reply:
            return json.loads(reply.read())

    def get(self, path: str) -> dict[str, Any]:
        with urllib.request.urlopen(self.base + path) as reply:
            return json.loads(reply.read())

    def app_id(self, model_id: str) -> str:
        known = self.app_ids.get(model_id)
        if known is None:
            known = f"{model_id}-{secrets.token_hex(4)}"[:12]
            self.app_ids[model_id] = known
            self.model_ids[known] = model_id
        return known

    def push(self, step: Any) -> Done:
        fixture: Push = step.of
        model_id = handle(fixture.container_id)
        body: dict[str, Any] = {"container_id": self.app_id(model_id) if model_id else ""}
        for name in FIELDS:
            value = getattr(fixture, name)
            if value is not None:
                body[name] = value
        reply = self.post(f"/push/{PUSHES[type(step)]}", body)
        if model_id:
            self.shows(self.app_id(model_id))
        return Done(self.rows(), (Ack(bool(reply["ok"])),))

    def shows(self, app_id: str) -> None:
        runs = self.get("/api/state")["runs"]
        want = next((r for r in runs if r["id"] == app_id), None)
        self.browser.page.wait_for_function(SHOWS, arg=[app_id, want, list(SHELL_KEYS)])
        self.settle()

    def perform(self, step: Interaction) -> Done | Refusal:
        if type(step) in PUSHES:
            return self.push(step)
        if isinstance(step, FilterTheList):
            query: Query = step.of
            self.browser.fill(Runs.filter, query.q or "")
            self.settle()
        elif isinstance(step, OpenSettings):
            self.browser.press(Runs.settings)
            self.browser.wait_for(SettingsScreen.root)
        elif isinstance(step, OpenRuns):
            self.browser.press(SettingsScreen.runs)
            self.browser.wait_for(Runs.root)
        elif isinstance(step, SwitchTheAttendant):
            self.switch(step.of)
        elif isinstance(step, OpenRun):
            self.open_run(step.of)
        elif isinstance(step, AnswerTheGate):
            return self.answer(step.of)
        elif isinstance(step, OpenHistory):
            self.pane("history", History.root)
        elif isinstance(step, OpenAttendant):
            self.pane("attend", Attendant.root)
        elif isinstance(step, OpenDispatch):
            self.pane("dispatch", Dispatch.root)
        return Done(self.rows())

    def pane(self, mode: str, root: object) -> None:
        self.browser.page.click(f"#activitybar .act-btn[data-mode={mode}]")
        self.browser.wait_for(root)
        self.settle()

    def open_run(self, run: Push) -> None:
        app_id = self.app_id(handle(run.container_id))
        if not self.browser.visible(Runs.root):
            self.browser.page.click("#activitybar .act-btn[data-mode=runs]")
            self.browser.wait_for(Runs.root)
        self.browser.page.click(f'#runs-list button.row[data-worker-id="{app_id}"]')
        self.browser.page.wait_for_selector(f'#detail .run-id:text-is("{app_id}")')
        self.settle()

    def answer(self, reply: Reply) -> Done | Refusal:
        self.open_run(Push(container_id=reply.container_id))
        self.browser.fill(RunDetail.answer, reply.answer or "")
        self.browser.press(RunDetail.send)
        self.browser.wait_for(RunDetail.rejected, "visible")
        shown = self.browser.text(RunDetail.rejected).splitlines()
        self.settle()
        return Refusal(shown[-1], 400)

    def switch(self, settings: Settings) -> None:
        want = bool(settings.enabled)
        if not self.browser.visible(SettingsScreen.root):
            self.browser.press(Runs.settings)
            self.browser.wait_for(SettingsScreen.root)
        box = self.browser.locate(SettingsScreen.attend)
        if box.is_checked() != want:
            with self.browser.answered(answer("POST", "/api/settings/attend")):
                self.browser.press(SettingsScreen.attend)
        mode = "headless" if want else "off"
        self.browser.page.wait_for_function(
            "(mode) => { const m = document.querySelector('#setting-attend .setting-mode'); return Boolean(m) && m.textContent === mode; }",
            arg=mode,
        )
        self.settle()

    def rows(self) -> tuple[object, ...]:
        seen = self.browser.page.evaluate(READ)
        lines: list[object] = []
        for row in seen["rows"]:
            model_id = self.model_ids.get(row["id"])
            if model_id is None:
                continue
            shown = row["wid"].removeprefix("#")
            row_id = model_id[:4] if shown == row["id"][:4] else shown
            lines.append(Line(model_id, row["state"], row["live"], row["repo"], row_id, row["label"], row["doing"]))
        return (*lines, Panel(seen["mode"]))
