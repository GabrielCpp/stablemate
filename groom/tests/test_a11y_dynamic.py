"""Accessibility, measured on the page the operator actually gets."""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AXE = Path(__file__).resolve().parent / "vendor" / "axe.min.js"

MODES = ("runs", "settings")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
        cwd=cwd, check=True, capture_output=True,
    )


def _workspace(base: Path) -> Path:
    """A workspace volume the way a native run leaves one: a checkout under it, committed, then dirtied — so /files has a tree and /diff has a diff."""
    repo = base / "acme"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("def main():\n    return 1\n")
    (repo / "README.md").write_text("# acme\n\nA placeholder checkout.\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    (repo / "src" / "app.py").write_text("def main():\n    return 2\n")
    return base


def _seed(workspace: Path) -> None:
    """Three runs covering every row state, one of them blocked on a gate whose question is markdown — that gate is what puts the answer form on the page."""
    from groom import state, store
    from groom.models import GateInfo, WorkflowState

    state.WORKFLOWS.clear()
    state.SCANNING = False

    blocked = state.upsert_workflow(
        "acme12345678",
        name="coder-acme",
        workflow_type="coder",
        repo_name="acme",
        repo_branch="main",
        current_node="await_operator",
        activity="waiting on the operator",
        run_id="run-blocked",
        state=WorkflowState.BLOCKED,
        native=True,
        workspace_volume=str(workspace),
        runs_volume=str(workspace),
    )
    blocked.gates["context/gate.md"] = GateInfo(
        workflow_id="acme12345678",
        file_path="context/gate.md",
        question="Pick a **storage backend**:\n\n- postgres\n- sqlite\n",
    )
    state.upsert_workflow(
        "globex123456",
        name="author-globex",
        workflow_type="author",
        repo_name="globex",
        repo_branch="feat/split",
        current_node="split_stories",
        activity="splitting stories",
        run_id="run-running",
        state=WorkflowState.RUNNING,
        native=True,
        workspace_volume=str(workspace),
    )
    state.upsert_workflow(
        "webapp123456",
        name="coder-web-app",
        workflow_type="coder",
        repo_name="web-app",
        current_node="done",
        run_id="run-done",
        state=WorkflowState.FINISHED,
        exit_code=0,
    )

    now = time.time()
    store.insert_spans(
        [
            {
                "span_id": f"span{i:04d}", "trace_id": "trace0001", "parent_id": "",
                "run_id": "run-running", "workflow": "author", "repo": "globex",
                "branch": "main", "node": f"node-{i}", "name": f"node-{i}",
                "run_dir": "", "start_ts": now - 60 + i, "end_ts": now - 59 + i,
                "status": "ERROR" if i % 5 == 0 else "OK", "attrs": {"gas": i},
            }
            for i in range(12)
        ]
    )
    from groom import alerts

    alerts.ingest_metrics(
        [
            {
                "run_id": "run-running", "name": "workhorse.run.heartbeat",
                "ts": now, "value": 1.0, "attrs": {"node": "split_stories"},
            },
            {
                "run_id": "run-blocked", "name": "workhorse.node.active",
                "ts": now, "value": 1.0, "attrs": {"node": "await_operator"},
            },
            {
                "run_id": "run-blocked", "name": "workhorse.wait.active",
                "ts": now, "value": 1.0,
                "attrs": {
                    "node": "await_operator", "wait_kind": "operator",
                    "gate_path": "context/gate.md",
                    "gate_question": "Pick a **storage backend**:\n\n- postgres\n- sqlite\n",
                },
            },
            {
                "run_id": "run-blocked", "name": "workhorse.wait.elapsed_s",
                "ts": now, "value": 125.0,
                "attrs": {"node": "await_operator", "wait_kind": "operator"},
            },
        ],
        now=now,
    )
    _seed_costed_run(now)


def _seed_costed_run(now: float) -> None:
    """One run with a finished state, a retried priced node, and work whose parent never ended."""
    from groom import store

    def span(span_id: str, parent: str, node: str, name: str, attrs: dict, at: float) -> dict:
        return {
            "span_id": span_id, "trace_id": "trace-cost", "parent_id": parent,
            "run_id": "run-blocked", "workflow": "coder", "repo": "acme", "branch": "main",
            "node": node, "name": name, "run_dir": "", "start_ts": at, "end_ts": at + 60,
            "status": "OK", "attrs": attrs,
        }

    turn = {"backend": "claude", "duration_ms": 60000, "usage.output_tokens": 1000}
    store.insert_spans(
        [
            span("cost-s0", "", "work", "work", {"workhorse.span_kind": "state", "workhorse.depth": 0}, now - 500),
            span("cost-n1", "cost-s0", "qa-story", "qa-story", {"workhorse.depth": 1}, now - 490),
            span("cost-t1", "cost-n1", "qa-story", "agent_turn", {**turn, "total_cost_usd": 1.5}, now - 480),
            span("cost-t2", "cost-n1", "qa-story", "agent_turn", {**turn, "total_cost_usd": 0.5}, now - 410),
            span("cost-n2", "never-exported", "dev-build", "dev-build", {"workhorse.depth": 2}, now - 300),
            span("cost-t3", "cost-n2", "dev-build", "agent_turn", dict(turn), now - 290),
        ]
    )


class _Live:
    """The booted dashboard: server thread, browser, and the temp dirs both own."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        os.environ["GROOM_DB"] = str(base / "groom.db")

        from groom import app as app_module
        from groom import store

        store.reset()
        workspace = _workspace(base / "ws")

        async def _no_archive() -> None:
            return None

        async def _no_reconcile() -> int:
            return 0

        self._app_module = app_module
        self._reconcile_patch = patch.object(app_module, "_reconcile", _no_reconcile)
        self._reconcile_patch.start()
        self._archive_patch = patch.object(app_module, "_spawn_archive", _no_archive)
        self._archive_patch.start()
        self._summaries_patch = patch.object(app_module, "_spawn_summaries", _no_archive)
        self._summaries_patch.start()
        _seed(workspace)

        import uvicorn

        self.port = _free_port()
        config = uvicorn.Config(
            app_module.create_app(), host="127.0.0.1", port=self.port, log_level="error"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self._await_port()

        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()

    def _await_port(self, timeout: float = 20.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("groom did not bind its port")

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def close(self) -> None:
        try:
            self.browser.close()
            self.pw.stop()
        finally:
            self._reconcile_patch.stop()
            self._archive_patch.stop()
            self._summaries_patch.stop()
            self.server.should_exit = True
            self.thread.join(timeout=10)
            self.tmp.cleanup()


_LIVE: _Live | None = None
_UNAVAILABLE = ""


def _live() -> _Live | None:
    """The shared dashboard, or None with a printed reason when this machine can't run it."""
    global _LIVE, _UNAVAILABLE
    if _LIVE is not None:
        return _LIVE
    if _UNAVAILABLE:
        print(f"SKIP  {_UNAVAILABLE}", file=sys.stderr)
        return None
    if not AXE.exists():
        _UNAVAILABLE = f"axe-core not vendored at {AXE}"
    else:
        try:
            _LIVE = _Live()
        except Exception as exc:  # noqa: BLE001 - any boot failure is a skip
            _UNAVAILABLE = f"cannot boot a live dashboard: {type(exc).__name__}: {exc}"
    if _LIVE is None:
        print(f"SKIP  {_UNAVAILABLE}", file=sys.stderr)
        return None
    return _LIVE


def teardown_module(module=None) -> None:
    """Stop the dashboard while the interpreter is still healthy."""
    global _LIVE
    if _LIVE is not None:
        _LIVE.close()
        _LIVE = None


def _open(live: _Live):
    """A page on the booted dashboard, with axe injected and the fleet rendered."""
    page = live.browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto(live.url(), wait_until="load")
    page.wait_for_selector("#runs-list .row", timeout=15000)
    page.add_script_tag(path=str(AXE))
    return page


_VIOLATIONS = """async () => {
  const r = await axe.run(document, { resultTypes: ["violations"] });
  return r.violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    targets: v.nodes.map((n) => n.target.join(" ")).slice(0, 6),
  }));
}"""


def _scan(page) -> list[dict]:
    return page.evaluate(_VIOLATIONS)


def _report(mode: str, violations: list[dict]) -> str:
    lines = [f"{mode}: {len(violations)} axe violation(s)"]
    for v in violations:
        lines.append(f"  [{v['impact']}] {v['id']}: {v['help']}")
        lines.extend(f"      {t}" for t in v["targets"])
    return "\n".join(lines)


def _drive(page, mode: str) -> None:
    """Put the page in ``mode`` with that pane's content actually loaded — an empty pane passes axe trivially and proves nothing."""
    page.click(f'.act-btn[data-mode="{mode}"]')
    if mode == "runs":
        page.click("#runs-list .row.blocked")
        page.wait_for_selector("form[data-answer] textarea", timeout=10000)


def _check_mode(mode: str) -> None:
    live = _live()
    if live is None:
        return
    page = _open(live)
    try:
        _drive(page, mode)
        violations = _scan(page)
        assert not violations, _report(mode, violations)
    finally:
        page.close()


def test_runs_pane_with_an_open_gate_is_accessible():
    _check_mode("runs")


def test_the_run_shows_loading_then_its_tabs_without_a_telemetry_feed():
    from playwright.sync_api import expect

    from groom import store

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    release = threading.Event()
    original = store.detail_metrics

    def held(run: str, limit: int = 60) -> list[dict]:
        assert release.wait(timeout=10)
        return original(run, limit)

    try:
        with patch.object(store, "detail_metrics", held):
            page.get_by_role("button", name=re.compile("author")).click()
            expect(page.get_by_role("status", name="Loading the run")).to_be_visible()
            release.set()
            expect(page.get_by_role("tab", name="Overview")).to_have_attribute("aria-selected", "true")
            expect(page.get_by_role("tab")).to_have_text([re.compile("^Overview$"), re.compile("^Activity")])
            expect(page.get_by_role("log", name="Telemetry history")).to_have_count(0)
            assert not _scan(page)
    finally:
        release.set()
        page.close()

def _box(locator) -> dict:
    box = locator.bounding_box()
    assert box is not None
    return box


def _pick(page, name: str):
    page.get_by_role("button", name=re.compile(name)).click()


def test_selecting_a_run_narrows_the_list_and_close_restores_it_with_its_filter():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        full = _box(page.locator("#runs"))["width"]
        page.get_by_role("searchbox", name="Filter runs").fill("acme")
        expect(page.locator("#runs-list .row")).to_have_count(1)
        _pick(page, "acme")
        expect(page.get_by_role("tab", name="Overview")).to_have_attribute("aria-selected", "true")
        expect(page.get_by_role("tab", name="Activity")).to_have_attribute("aria-selected", "false")
        assert _box(page.locator("#runs"))["width"] < full / 2
        page.get_by_role("button", name="Close run detail").click()
        expect(page.locator("#detail")).to_be_hidden()
        assert _box(page.locator("#runs"))["width"] >= full - 2
        expect(page.get_by_role("searchbox", name="Filter runs")).to_have_value("acme")
        expect(page.locator("#runs-list .row")).to_have_count(1)
    finally:
        page.close()


def test_j_and_k_and_the_filter_work_in_the_narrowed_list():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        _pick(page, "acme")
        page.keyboard.press("j")
        expect(page.locator("#runs-list .row.selected")).not_to_contain_text("acme")
        page.keyboard.press("k")
        expect(page.locator("#runs-list .row.selected")).to_contain_text("acme")
        page.get_by_role("searchbox", name="Filter runs").fill("globex")
        expect(page.locator("#runs-list .row")).to_have_count(1)
    finally:
        page.close()


def test_tabs_switch_with_the_arrow_keys_and_details_keeps_todays_content():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        _pick(page, "author")
        overview = page.get_by_role("tab", name="Overview")
        overview.focus()
        page.keyboard.press("ArrowRight")
        activity = page.get_by_role("tab", name="Activity")
        expect(activity).to_be_focused()
        expect(activity).to_have_attribute("aria-selected", "true")
        page.keyboard.press("ArrowLeft")
        expect(overview).to_have_attribute("aria-selected", "true")
    finally:
        page.close()


def test_a_blocked_runs_gate_sits_above_the_tabs_and_can_be_answered_there():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        strip = page.get_by_role("region", name="Open gates")
        expect(strip).to_contain_text("storage backend")
        assert _box(strip)["y"] < _box(page.get_by_role("tablist"))["y"]
        strip.get_by_role("textbox").fill("sqlite")
        strip.get_by_role("button", name=re.compile("send|answer", re.I)).click()
        toast = page.wait_for_selector("#toasts .toast.blocked", timeout=10000)
        assert toast is not None
        assert toast.inner_text().splitlines()[0] == "✗ answer not taken"
    finally:
        page.close()


def test_overview_shows_real_cost_coverage_and_the_flow_tree():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        panel = page.get_by_role("tabpanel")
        expect(panel).to_contain_text("$2.00")
        expect(panel).to_contain_text("2 of 3 turns priced")
        expect(panel).to_contain_text("as of the last finished turn")
        table = page.get_by_role("table", name="Time and cost per flow")
        expect(table).to_contain_text("Unfinished flow or state")
        expect(table.get_by_role("row", name=re.compile("work › qa-story"))).to_contain_text("$2.00")
        retries = table.get_by_role("row", name=re.compile("work › qa-story")).locator("td").last
        expect(retries).to_have_text("1")
        table.get_by_role("button", name="Expand Unfinished flow or state").count()
        expect(table).to_contain_text("dev-build")
        assert not _scan(page)
    finally:
        page.close()


def test_the_node_waiting_on_the_operator_is_marked_in_words_not_as_running():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        table = page.get_by_role("table", name="Time and cost per flow")
        mark = table.get_by_role("row", name=re.compile("await_operator"))
        expect(mark).to_contain_text("waiting on the operator")
        expect(mark).not_to_contain_text("running")
    finally:
        page.close()


def test_a_running_node_is_marked_running_with_its_time():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        _pick(page, "author")
        table = page.get_by_role("table", name="Time and cost per flow")
        expect(table.get_by_role("row", name=re.compile("split_stories"))).to_contain_text("running")
    finally:
        page.close()


def test_a_backend_that_reports_no_cost_says_so_and_the_tree_shows_output_tokens():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        _pick(page, "author")
        panel = page.get_by_role("tabpanel")
        expect(panel).to_contain_text("reports no cost")
        expect(panel).not_to_contain_text("$0")
        expect(page.get_by_role("table", name="Time and cost per flow").get_by_role("columnheader", name="Output")).to_be_visible()
    finally:
        page.close()


def test_a_run_with_no_finished_node_says_figures_appear_when_one_finishes():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.get_by_role("button", name=re.compile("web-app")).click()
        panel = page.get_by_role("tabpanel")
        expect(panel).to_contain_text("Figures appear when the first node finishes")
        expect(panel).not_to_contain_text("$")
    finally:
        page.close()


def test_overview_says_it_is_reading_then_offers_a_retry_when_the_read_fails():
    from playwright.sync_api import expect

    from groom import store

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    release = threading.Event()
    calls: list[int] = []
    original = store.run_flows

    def flaky(run: str):
        calls.append(1)
        assert release.wait(timeout=10)
        if len(calls) <= 2:
            raise RuntimeError("store unavailable")
        return original(run)

    patcher = patch.object(store, "run_flows", flaky)
    patcher.start()
    try:
        page.click("#runs-list .row.blocked")
        expect(page.get_by_role("status").filter(has_text="Reading this run")).to_be_visible()
        release.set()
        alert = page.get_by_role("tabpanel").get_by_role("alert")
        expect(alert).to_contain_text("could not be read")
        page.get_by_role("tab", name="Activity").click()
        page.get_by_role("tab", name="Overview").click()
        expect(page.get_by_role("tabpanel").get_by_role("alert")).to_contain_text("could not be read")
        page.get_by_role("button", name="Retry now").click()
        expect(page.get_by_role("tabpanel")).to_contain_text("$2.00")
        expect(page.get_by_role("tabpanel").get_by_role("alert")).to_have_count(0)
    finally:
        release.set()
        patcher.stop()
        page.close()


def _post_turn(
    live: _Live, span_id: str, *, usd: float, run: str = "run-blocked", workflow: str = "coder", node: str = "qa-story"
) -> None:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceRequest,
    )

    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    for key, value in {"run_id": run, "workflow": workflow}.items():
        kv = resource_spans.resource.attributes.add()
        kv.key, kv.value.string_value = key, value
    span = resource_spans.scope_spans.add().spans.add()
    span.trace_id = bytes.fromhex("ab" * 16)
    span.span_id = bytes.fromhex(span_id)
    span.name = "agent_turn"
    now = time.time()
    span.start_time_unix_nano = int((now - 5) * 1e9)
    span.end_time_unix_nano = int(now * 1e9)
    for key, value in {"workhorse.node": node, "backend": "claude"}.items():
        kv = span.attributes.add()
        kv.key, kv.value.string_value = key, value
    kv = span.attributes.add()
    kv.key, kv.value.double_value = "total_cost_usd", usd
    kv = span.attributes.add()
    kv.key, kv.value.int_value = "duration_ms", 5000
    http = urllib.request.Request(
        live.url() + "v1/traces",
        data=request.SerializeToString(),
        headers={"Content-Type": "application/x-protobuf"},
    )
    with urllib.request.urlopen(http, timeout=10) as reply:
        assert reply.status == 200


def _drop_turn(span_id: str) -> None:
    from groom import store

    store._chunked_delete("spans", "span_id = ?", (span_id,))


def test_the_time_cell_carries_a_proportional_bar_beside_the_duration():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        table = page.get_by_role("table", name="Time and cost per flow")
        row = table.get_by_role("row", name=re.compile("work › qa-story"))
        expect(row.locator(".tb u")).to_have_count(1)
        width = row.locator(".tb u").evaluate("el => parseFloat(el.style.width)")
        assert 0 < width <= 100
        expect(row.locator(".tb s")).to_have_attribute("aria-hidden", "true")
        expect(row.locator(".tb")).to_contain_text("s")
    finally:
        page.close()


def test_new_telemetry_updates_the_open_overview_and_keeps_the_operators_place():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.set_viewport_size({"width": 1400, "height": 330})
        page.click("#runs-list .row.blocked")
        panel = page.get_by_role("tabpanel")
        expect(panel).to_contain_text("$2.00")
        table = page.get_by_role("table", name="Time and cost per flow")
        table.get_by_role("button", name="Collapse coder").click()
        expect(table.get_by_role("button", name="Expand coder")).to_have_count(1)
        table.get_by_role("button", name="Expand coder").click()
        expect(table.get_by_role("button", name="Collapse coder")).to_have_count(1)
        table.get_by_role("button", name="Collapse Unfinished flow or state").click()
        panel.evaluate("el => { el.scrollTop = 40; }")
        scrolled = panel.evaluate("el => el.scrollTop")
        page.evaluate(
            "() => { window.__row = document.querySelector('table.tt tr.workflow');"
            " window.__row.dataset.mark = 'kept'; }"
        )
        _post_turn(live, "00000000000000a1", usd=1.5)
        expect(panel).to_contain_text("$3.50")
        expect(panel).to_contain_text("3 of 4 turns priced")
        assert panel.evaluate("el => el.scrollTop") == scrolled
        expect(table.get_by_role("button", name="Expand Unfinished flow or state")).to_have_count(1)
        assert page.evaluate("() => window.__row.isConnected && window.__row.dataset.mark") == "kept"
        expect(panel.locator("[aria-live]")).to_have_count(0)
        assert not _scan(page)
    finally:
        _drop_turn("00000000000000a1")
        page.close()


def test_the_time_since_the_last_finished_turn_counts_up_every_second():
    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        tile = page.locator("#detail-cost-tile .ss")
        first = tile.inner_text()
        deadline = time.time() + 4
        while time.time() < deadline and tile.inner_text() == first:
            time.sleep(0.2)
        assert tile.inner_text() != first
    finally:
        page.close()


def _seed_author_history(*, runs: int, step_seconds: float) -> None:
    from groom import norms, store

    for index in range(5):
        store.delete_run_telemetry(f"author-ok-{index}")
    spans = []
    for index in range(runs):
        run = f"author-ok-{index}"
        for node, name, seconds, attrs in (
            ("run:author", "run:author", 900.0, {"workhorse.terminal": "terminal"}),
            ("split_stories", "split_stories", step_seconds, {}),
        ):
            spans.append({
                "span_id": f"{run}-{node}", "trace_id": run, "parent_id": "", "run_id": run,
                "workflow": "author", "repo": "globex", "branch": "main", "node": node, "name": name,
                "run_dir": "", "start_ts": 1000.0, "end_ts": 1000.0 + seconds, "status": "OK", "attrs": attrs,
            })
    store.insert_spans(spans)
    norms.reset()


def _running_for(seconds: float) -> None:
    from groom import alerts

    now = time.time()
    alerts.ingest_metrics(
        [
            {"run_id": "run-running", "name": "workhorse.node.active", "ts": now, "value": 1.0,
             "attrs": {"node": "split_stories"}},
            {"run_id": "run-running", "name": "workhorse.node.elapsed_s", "ts": now, "value": seconds,
             "attrs": {"node": "split_stories"}},
        ],
        now=now,
    )


def _seconds_in(text: str) -> int:
    hours = re.search(r"(\d+)h", text, re.I)
    minutes = re.search(r"(\d+)m", text, re.I)
    secs = re.search(r"(\d+)s", text, re.I)
    return (int(hours[1]) * 3600 if hours else 0) + (int(minutes[1]) * 60 if minutes else 0) + (int(secs[1]) if secs else 0)


def _clock_readings(page) -> dict[str, int]:
    values = page.evaluate(
        """() => {
          const row = document.querySelector('#runs-list .row[aria-current="true"] .mini');
          const lead = document.querySelector('[aria-label="Where the run is now"] > div:nth-child(2) .v2');
          const mark = document.querySelector('table.tt tr.cur .chip');
          const cell = document.querySelector('table.tt tr.cur td:nth-child(3)');
          return [row, lead, mark, cell].map((el) => (el ? el.innerText : ''));
        }"""
    )
    row, strip, mark, cell = values
    return {
        "row": _seconds_in(row.split("·")[0]),
        "strip": _seconds_in(strip),
        "tree_mark": _seconds_in(mark),
        "tree_time": _seconds_in(cell),
    }


def _ingest_aged(run_id: str, node: str, points: dict[str, float], age: float, attrs: dict | None = None) -> None:
    from groom import alerts

    now = time.time()
    arrived = now - age
    alerts.ingest_metrics(
        [{"run_id": run_id, "name": name, "ts": arrived, "value": value, "attrs": {"node": node, **(attrs or {})}}
         for name, value in points.items()],
        now=arrived,
    )


def _assert_one_clock(page, expected: int | None) -> None:
    deadline = time.time() + 6
    readings: dict[str, int] = {}
    while time.time() < deadline:
        readings = _clock_readings(page)
        if len(set(readings.values())) == 1:
            break
        time.sleep(0.2)
    assert len(set(readings.values())) == 1, readings
    assert expected is None or expected <= readings["strip"] <= expected + 8, readings
    first = readings["strip"]
    deadline = time.time() + 10
    later = readings
    while time.time() < deadline:
        time.sleep(0.25)
        later = _clock_readings(page)
        if later["strip"] >= first + 2:
            break
    assert len(set(later.values())) == 1 and later["strip"] >= first + 2, (first, later)


def test_the_row_the_strip_and_the_tree_count_one_clock_for_a_step():
    live = _live()
    assert live is not None, _UNAVAILABLE
    _seed_author_history(runs=5, step_seconds=60.0)
    _ingest_aged("run-running", "split_stories", {"workhorse.node.active": 1.0, "workhorse.node.elapsed_s": 600.0}, age=30.0)
    page = _open(live)
    try:
        _pick(page, "author")
        page.get_by_role("group", name="Where the run is now").wait_for()
        _assert_one_clock(page, 630)
    finally:
        page.close()


def test_the_row_the_strip_and_the_tree_count_one_clock_for_a_turn():
    live = _live()
    assert live is not None, _UNAVAILABLE
    _seed_author_history(runs=5, step_seconds=60.0)
    _ingest_aged(
        "run-running", "split_stories",
        {"workhorse.node.active": 1.0, "workhorse.node.elapsed_s": 700.0, "workhorse.turn.active": 1.0,
         "workhorse.turn.elapsed_s": 700.0, "workhorse.turn.idle_s": 5.0},
        age=40.0,
    )
    page = _open(live)
    try:
        _pick(page, "author")
        page.get_by_role("group", name="Where the run is now").wait_for()
        _assert_one_clock(page, 740)
    finally:
        _ingest_aged("run-running", "split_stories", {"workhorse.turn.active": 0.0}, age=0.0)
        page.close()


def test_the_strip_says_a_step_is_longer_than_usual_in_words_and_its_counts_tick():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    _seed_author_history(runs=5, step_seconds=60.0)
    _running_for(600.0)
    page = _open(live)
    try:
        _pick(page, "author")
        strip = page.get_by_role("group", name="Where the run is now")
        expect(strip).to_contain_text("split_stories")
        expect(strip).to_contain_text("In step")
        expect(strip).to_contain_text("longer than usual: this step usually takes 1m 0s")
        expect(strip).to_contain_text("no agent in a step")
        assert _box(strip)["y"] < _box(page.get_by_role("table", name="Time and cost per flow"))["y"]
        first = strip.inner_text()
        deadline = time.time() + 4
        while time.time() < deadline and strip.inner_text() == first:
            time.sleep(0.2)
        assert strip.inner_text() != first
        assert not _scan(page)
    finally:
        page.close()


def test_the_strip_gives_the_comparable_run_count_when_there_is_no_norm_yet():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    _seed_author_history(runs=3, step_seconds=60.0)
    _running_for(30.0)
    page = _open(live)
    try:
        _pick(page, "author")
        strip = page.get_by_role("group", name="Where the run is now")
        expect(strip).to_contain_text("no norm yet: 3 comparable runs")
        expect(strip).not_to_contain_text("longer than usual")
    finally:
        page.close()


def test_a_run_blocked_at_a_gate_shows_the_wait_in_place_of_the_turn_with_no_norm():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        strip = page.get_by_role("group", name="Where the run is now")
        expect(strip).to_contain_text("Waiting on you")
        expect(strip).to_contain_text("no norm while waiting")
        expect(strip).not_to_contain_text("In turn")
        expect(strip).not_to_contain_text("usually takes")
        assert not _scan(page)
    finally:
        page.close()


def test_the_row_the_strip_and_the_tree_count_one_clock_for_a_gate_wait():
    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        page.get_by_role("group", name="Where the run is now").wait_for()
        _assert_one_clock(page, None)
    finally:
        page.close()


def test_settings_pane_is_accessible():
    _check_mode("settings")


def test_the_activity_rail_is_reachable_and_operable_by_keyboard():
    live = _live()
    if live is None:
        return
    page = _open(live)
    try:
        reached = page.evaluate(
            """() => {
              const btns = [...document.querySelectorAll("#activitybar .act-btn")];
              return btns.every((b) => b.tabIndex >= 0 && !b.disabled);
            }"""
        )
        assert reached, "an activity-rail button is not in the tab order"
        page.focus('.act-btn[data-mode="dispatch"]')
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.querySelector('.app').dataset.mode === 'dispatch'", timeout=5000)
        pressed = page.get_attribute('.act-btn[data-mode="dispatch"]', "aria-pressed")
        assert pressed == "true", "the rail does not announce which pane is current"
    finally:
        page.close()


def test_the_answer_form_is_reachable_and_submittable_by_keyboard():
    live = _live()
    if live is None:
        return
    page = _open(live)
    try:
        _drive(page, "runs")
        page.focus("form[data-answer] textarea")
        page.keyboard.type("sqlite")
        page.keyboard.press("Tab")
        landed = page.evaluate(
            """() => {
              const el = document.activeElement;
              return el && el.tagName === "BUTTON" && el.type === "submit"
                && el.closest("form[data-answer]") !== null;
            }"""
        )
        assert landed, "Tab out of the answer textarea does not reach its submit button"
        page.keyboard.press("Enter")
        toast = page.wait_for_selector("#toasts .toast.blocked", timeout=10000)
        assert toast is not None
        assert toast.inner_text().splitlines()[0] == "✗ answer not taken"
    finally:
        page.close()


def test_a_rejected_answer_toasts_the_reason_to_the_sending_tab_alone():
    live = _live()
    if live is None:
        return
    sender = _open(live)
    bystander = _open(live)
    try:
        _drive(sender, "runs")
        sender.fill("form[data-answer] textarea", "sqlite")
        sender.click("form[data-answer] button[type=submit]")
        toast = sender.wait_for_selector("#toasts .toast.blocked", timeout=10000)
        assert toast is not None
        assert toast.inner_text().splitlines() == ["✗ answer not taken", "gate file not found"]
        bystander.wait_for_timeout(500)
        assert bystander.query_selector("#toasts .toast") is None
    finally:
        sender.close()
        bystander.close()


def test_a_rejected_answer_puts_the_typed_text_back_in_its_box():
    live = _live()
    if live is None:
        return
    page = _open(live)
    try:
        _drive(page, "runs")
        page.fill("form[data-answer] textarea", "sqlite")
        page.click("form[data-answer] button[type=submit]")
        page.wait_for_selector("#toasts .toast.blocked", timeout=10000)
        assert page.input_value("form[data-answer] textarea") == "sqlite"
    finally:
        page.close()


_DISPATCH_CONFIG = """[groom.dispatch.plans]
command = "workhorse-loop-runner"
[[groom.dispatch.plans.params]]
name = "plan"
label = "Plan path"
required = true
[[groom.dispatch.plans.params]]
name = "cli"
label = "Agent CLI"
type = "select"
options = ["claude", "codex"]
"""


def _focus_in_dialog(page) -> bool:
    return page.evaluate(
        "() => document.getElementById('dispatch-enqueue-modal').contains(document.activeElement)"
    )


def test_the_dispatch_pane_is_operable_by_keyboard_and_its_dialog_holds_focus():
    from playwright.sync_api import expect

    from groom import dispatch_ledger

    live = _live()
    assert live is not None, _UNAVAILABLE
    config = Path(live.tmp.name) / "dispatch.toml"
    config.write_text(_DISPATCH_CONFIG)
    with patch.dict(os.environ, {"STABLEMATE_CONFIG": str(config)}):
        dispatch_ledger.dispatch_enqueue(
            "item-pending", queue="plans", command="workhorse-loop-runner", params={"plan": "p.md"}
        )
        page = _open(live)
        try:
            page.click('.act-btn[data-mode="dispatch"]')
            page.get_by_role("button", name=re.compile("plans")).click()
            item = page.get_by_role("button", name=re.compile("item-pending"))
            item.focus()
            page.keyboard.press("Enter")
            expect(item).to_have_attribute("aria-current", "true")
            expect(page.locator("#dispatch-detail")).to_contain_text("p.md")
            assert not _scan(page)

            new_run = page.get_by_role("button", name="New run", exact=True)
            new_run.focus()
            page.keyboard.press("Enter")
            dialog = page.get_by_role("dialog", name="New dispatch run")
            expect(dialog).to_be_visible()
            plan = dialog.get_by_role("textbox", name="Plan path")
            expect(plan).to_be_focused()
            expect(dialog.get_by_role("combobox", name="Agent CLI")).to_be_visible()
            assert not _scan(page)

            for _ in range(6):
                page.keyboard.press("Tab")
                assert _focus_in_dialog(page), "Tab left the open dispatch dialog"
            plan.focus()
            page.keyboard.press("Shift+Tab")
            assert _focus_in_dialog(page), "Shift+Tab left the open dispatch dialog"

            page.keyboard.press("Escape")
            expect(dialog).to_be_hidden()
            expect(new_run).to_be_focused()

            new_run.click()
            expect(plan).to_be_focused()
            page.mouse.click(5, 5)
            expect(dialog).to_be_hidden()
            expect(new_run).to_be_focused()
        finally:
            page.close()
            dispatch_ledger.dispatch_cancel_pending("item-pending")


if __name__ == "__main__":
    failed = 0
    try:
        for name, fn in sorted(list(globals().items())):
            if not name.startswith("test_") or not callable(fn):
                continue
            try:
                fn()
                print(f"PASS  {name}")
            except Exception as exc:  # noqa: BLE001 - report and keep going
                failed += 1
                print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    finally:
        teardown_module()
    total = len([n for n in globals() if n.startswith("test_")])
    print(f"\n{total - failed}/{total} passed")
    raise SystemExit(1 if failed else 0)


def test_the_five_tiles_read_the_runs_standing():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        expect(page.locator("#detail-cost-tile")).to_contain_text("$2.00")
        expect(page.locator("#detail-cost-tile")).to_contain_text("per active hour")
        expect(page.locator("#detail-active-tile")).to_contain_text("wall")
        expect(page.locator("#detail-active-tile")).to_contain_text("session")
        expect(page.locator("#detail-turns-tile")).to_have_text(re.compile(r"Agent turns\s*3\s*1 backend retry"))
        attention = page.locator("#detail-attention-tile")
        expect(attention).to_contain_text("1 gate")
        expect(attention).to_contain_text("waiting")
        expect(attention).to_contain_text("problem")
        assert not _scan(page)
    finally:
        page.close()


def test_the_attention_tile_waits_as_long_as_the_tree_says():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        mark = page.get_by_role("table", name="Time and cost per flow").get_by_role("row", name=re.compile("await_operator"))
        expect(mark).to_contain_text("waiting on the operator")
        deadline = time.time() + 8
        tile = tree = -1
        while time.time() < deadline:
            tile = _seconds_in(page.locator("#detail-attention-tile .ss").inner_text().split("·")[0])
            tree = _seconds_in(mark.inner_text().split("waiting on the operator")[-1])
            if tile == tree and tile > 0:
                break
            time.sleep(0.2)
        assert tile == tree and tile > 0, (tile, tree)
    finally:
        page.close()


def test_a_run_with_no_finished_node_shows_no_tiles_and_no_problem_count():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.get_by_role("button", name=re.compile("web-app")).click()
        expect(page.get_by_role("tabpanel")).to_contain_text("Figures appear when the first node finishes")
        expect(page.locator("#detail-attention-tile")).to_have_count(0)
        expect(page.locator(".kpi")).to_have_count(0)
        expect(page.get_by_role("tabpanel")).not_to_contain_text("problem")
    finally:
        page.close()


def test_a_backend_with_no_cost_labels_its_estimate_and_gives_no_cost_per_item():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        _pick(page, "author")
        cost = page.locator("#detail-cost-tile")
        expect(cost).to_contain_text("reports no cost")
        text = cost.inner_text()
        assert "est" not in text or "at list price" in text, text
        expect(page.locator("#detail-items-tile")).not_to_contain_text("per finished item")
    finally:
        page.close()


def test_the_tiles_refresh_in_place_when_a_turn_lands():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        page.click("#runs-list .row.blocked")
        expect(page.locator("#detail-turns-tile .vv")).to_have_text("3")
        _post_turn(live, "00000000000000b2", usd=1.0)
        expect(page.locator("#detail-turns-tile .vv")).to_have_text("4", timeout=15000)
        expect(page.locator("#detail-cost-tile")).to_contain_text("$3.00")
    finally:
        _drop_turn("00000000000000b2")
        page.close()
