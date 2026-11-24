"""The dashboard in a browser. Pushes reach groom the way a workflow sends them, over HTTP,
and the page is read for what it shows."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import time
import urllib.request
from contextlib import closing
from typing import Any

from ostler.book import Browser, Done, Environment, PageSurface, Refusal, answer
from ostler.book.screen import Interaction

from ..fixtures import Judged, Push, Query, Reply, Settings
from ..model.actions import handle
from ..model.records import Ack, Line, Panel
from ..stack import DB
from .activity import Note
from .median import ITEMS, PEER_VISIT, EachCell, MedianCell, NodeCells, TileCell
from .interactions import (
    AnswerTheGate, FilterTheList, ReadActivity, ReadTheMedian, ReadTheOpenedRun, OpenAttendant, OpenDispatch, OpenHistory, OpenRun, OpenRuns, OpenSettings, ReportExit,
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
        if (!body) return;
        if (body.type === "state" && Array.isArray(body.runs)) {
          window.__shell = { runs: body.runs.slice() };
        } else if (window.__shell && body.type === "run" && body.run) {
          const rest = window.__shell.runs.filter((r) => r.id !== body.run.id);
          window.__shell = { runs: rest.concat([body.run]) };
        } else if (window.__shell && body.type === "run_removed") {
          window.__shell = { runs: window.__shell.runs.filter((r) => r.id !== body.id) };
        }
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

EACH = """
([run]) => {
  const th = document.querySelector('#history table.ht th[title^="Per finished item"]');
  const row = [...document.querySelectorAll('#history tr.hrow')].find((r) => r.innerText.includes(run));
  return row && th ? row.cells[th.cellIndex].innerText : null;
}
"""

MEDIAN = '#history .h-sum span[title^="Successful runs of this workflow"]'

OLD = 10 * 86400.0

SUMMARY = (
    "run_id", "workflow", "repo", "branch", "state", "ending", "ended_ts", "last_ts", "active_s", "wall_s",
    "cost_usd", "est_usd", "priced_turns", "turns", "items_done", "items_total", "nodes_json",
)

NODE_TABLE = 'table[aria-label="Time and cost per node"]'
TILE = "#detail-items-tile"
BREAKDOWN = '[role=group][aria-label="Breakdown view"] button:text-is("By node")'
HEADING = f"{NODE_TABLE} thead th:nth-child(6)"
NODE_CELL = """
([name]) => {
  const row = [...document.querySelectorAll('table[aria-label="Time and cost per node"] tbody tr')].find((r) => r.cells[0].innerText.trim() === name);
  return row ? row.cells[5].innerText : null;
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
        elif isinstance(step, ReadActivity):
            return self.activity()
        elif isinstance(step, ReadTheMedian):
            return self.median(step.of)
        elif isinstance(step, ReadTheOpenedRun):
            return self.opened(step.of)
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

    def activity(self) -> Done:
        self.browser.page.click("#tab-activity")
        note = self.browser.page.locator('#detail-panel[aria-labelledby="tab-activity"] .empty-big[role="status"]')
        note.wait_for()
        text = note.inner_text().strip()
        self.settle()
        return Done(self.rows(), (Note(text),))

    def summaries(self, judged: Judged, workflow: str, own: str) -> None:
        now = time.time()
        each = [(f"peer{n}-{own.removeprefix('judged-')}", cost, False, 2, 1, PEER_VISIT) for n, cost in enumerate(judged.peers)]
        each.append((own, judged.each, judged.estimate, judged.items, 1 if judged.priced and not judged.estimate else 0, judged.visit))
        rows = []
        spans = []
        for n, (run, cost, estimate, items, priced, visit) in enumerate(each):
            ended = now - 3600 * (n + 1) - (OLD if judged.aged and run != own else 0)
            ending = judged.ending if run == own else "success"
            unpriced = run == own and not judged.priced
            spent = None if estimate or unpriced else cost * items
            guess = cost * items if estimate else None
            node = {"node": "qa", "kind": "agent", "visits": 1, "time_s": visit, "samples": 1, "longest_s": visit, "turns": 1, "cost_turns": priced, "cost_usd": spent, "output_tokens": 100, "retries": 0}
            rows.append((run, workflow, "acme", "main", "ready", ending, ended, ended, 3600.0, 7200.0, spent, guess, min(priced, 1) if judged.partly else 4 * priced, 4, items, items, json.dumps([node])))
            if run == own:
                spans = self.spans(run, workflow, ended - 1000, judged, spent)
        marks = ", ".join("?" for _ in SUMMARY)
        with closing(sqlite3.connect(DB, timeout=10)) as conn, conn:
            conn.executemany(f"INSERT OR REPLACE INTO spans (span_id, trace_id, parent_id, run_id, workflow, repo, branch, node, name, run_dir, start_ts, end_ts, status, attrs_json, resume_generation) VALUES ({', '.join('?' for _ in range(15))})", spans)  # noqa: S608
            conn.executemany(f"INSERT OR REPLACE INTO run_summary ({', '.join(SUMMARY)}) VALUES ({marks})", rows)  # noqa: S608

    def spans(self, run: str, workflow: str, base: float, judged: Judged, spent: float | None) -> list[tuple[Any, ...]]:
        terminal = "terminal" if judged.ending == "success" else "fail"
        turn = {"backend": "claude", "model": "claude-sonnet-5", "duration_ms": judged.visit * 1000, "usage.output_tokens": 100}
        if spent is not None:
            turn["total_cost_usd"] = spent
        found = (
            ("r", "", "coder", "run:coder", 1000.0, {"workhorse.terminal": terminal, "progress": f"{judged.items}/{ITEMS}"}),
            ("s", "r", "work", "work", 900.0, {"workhorse.span_kind": "state", "workhorse.depth": 0}),
            ("n", "s", "qa", "qa", 800.0, {"workhorse.depth": 1}),
            ("a", "n", "qa", "agent_turn", judged.visit, turn),
            ("d", "s", "lint", "lint", 30.0, {}),
        )
        return [
            (f"{run}-{key}", f"{run}-t", f"{run}-{parent}" if parent else "", run, workflow, "acme", "main", node, name, "", base + 10 * index, base + 10 * index + seconds, "OK", json.dumps(attrs), 1)
            for index, (key, parent, node, name, seconds, attrs) in enumerate(found)
        ]

    def judge(self, judged: Judged) -> tuple[str, str]:
        tag = secrets.token_hex(3)
        workflow, own = f"{judged.workflow}-{tag}", f"judged-{tag}"
        self.summaries(judged, workflow, own)
        self.browser.page.click("#activitybar .act-btn[data-mode=runs]")
        self.pane("history", History.root)
        close = self.browser.page.locator("#history-close")
        if close.is_visible():
            close.click()
        self.browser.wait_for(History.workflow)
        self.browser.fill(History.workflow, "")
        self.browser.page.wait_for_selector(f"#history tr.hrow:has-text('{own}')")
        self.browser.fill(History.workflow, workflow)
        self.browser.fill(History.range, "7" if judged.aged else "30")
        return workflow, own

    def express(self, request: Any, outcome: Done) -> tuple[object, ...] | None:
        return None if isinstance(request, FilterTheList) else outcome.view

    def median(self, judged: Judged) -> Done:
        workflow, own = self.judge(judged)
        cell = self.browser.page.locator(MEDIAN)
        cell.wait_for()
        each = self.browser.page.evaluate(EACH, [own])
        totals = " ".join(cell.inner_text().split())
        self.settle()
        return Done(self.rows(), (EachCell(" ".join(each.split())), MedianCell(totals.replace(workflow, judged.workflow))))

    def opened(self, judged: Judged) -> Done:
        workflow, own = self.judge(judged)
        page = self.browser.page
        page.click(f"#history tr.hrow:has-text('{own}')")
        page.wait_for_selector(f"#history-detail {TILE}")
        tile = re.sub(r"^work items ", "", " ".join(page.locator(TILE).inner_text().split()), flags=re.IGNORECASE)
        page.click(BREAKDOWN)
        page.wait_for_selector(NODE_TABLE)
        heading = " ".join((page.locator(HEADING).text_content() or "").split())
        agent = page.evaluate(NODE_CELL, ["qa"])
        step = page.evaluate(NODE_CELL, ["lint"])
        self.settle()
        shown = (TileCell(tile.replace(workflow, judged.workflow)), NodeCells(heading, " ".join(agent.split()), " ".join(step.split())))
        return Done(self.rows(), shown)

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
