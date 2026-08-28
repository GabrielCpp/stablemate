"""Accessibility, measured on the page the operator actually gets.

groom used to lint its accessibility statically, by parsing ``dashboard.html``
with a hand-rolled tag scanner. That worked while the shell *was* the dashboard.
It stopped working the moment the panes became Preact islands: the template now
ships five empty divs, and every control an operator can reach — run rows, the
answer form, the repo listbox, the file tree, the diff, the trace rows — is
created by JavaScript from JSON that arrives over a socket. A static reader of
the template sees none of it, so a green static lint said nothing at all.

So this boots a real groom over a synthetic fleet, drives a real Chromium through
each pane, and runs axe-core against the live DOM. axe is vendored under
``tests/vendor/`` — nothing here reaches a CDN, in a test or otherwise.

Scanning ``document`` per mode is deliberate rather than lazy: inactive panes are
``display:none``, which axe already excludes, so one scan per mode covers that
mode's pane *plus* the shell around it (activity rail, status bar, toasts) and
catches a shell regression five times over.

Requires: playwright + its chromium (``uv run playwright install chromium``).
Skips cleanly, loudly, when either is missing.

Run: uv run pytest tests/test_a11y_dynamic.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
AXE = Path(__file__).resolve().parent / "vendor" / "axe.min.js"

# The panes an operator can reach, and how to get there. Each entry is scanned
# with axe after `_goto` has driven the page into that state.
MODES = ("runs", "files", "diff", "telemetry", "settings")


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
    """A workspace volume the way a native run leaves one: a checkout under it,
    committed, then dirtied — so /files has a tree and /diff has a diff."""
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
    """Three runs covering every row state, one of them blocked on a gate whose
    question is markdown — that gate is what puts the answer form on the page."""
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
    # A heartbeat inside the live window: the telemetry pane shows the runs that
    # are connected *now*, so span history alone leaves it empty. Liveness is
    # memory-only — the beat goes into the ingest cache, never the store.
    from groom import alerts

    alerts.ingest_metrics(
        [
            {
                "run_id": "run-running", "name": "workhorse.run.heartbeat",
                "ts": now, "value": 1.0, "attrs": {"node": "split_stories"},
            }
        ],
        now=now,
    )


class _Live:
    """The booted dashboard: server thread, browser, and the temp dirs both own.

    Built once and shared by every test in the file. A browser launch plus a
    lifespan startup is ~2s; paying it five times to prove the same five panes
    accessible is time spent on nothing.
    """

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        os.environ["GROOM_DB"] = str(base / "groom.db")

        from groom import app as app_module
        from groom import store

        store.reset()
        workspace = _workspace(base / "ws")

        # Startup would otherwise run the docker discovery pass, which prunes the
        # synthetic fleet on its way past. Everything else about the real app —
        # the 5s live tick, the rules ticker, the routes — is left alone.
        async def _no_reconcile() -> int:
            return 0  # the real one answers with how many containers it found

        # Stopped in close(): this is a module attribute, not a fixture, so a stub
        # left behind would silently disarm /refresh for every later test in the
        # session.
        self._app_module = app_module
        self._reconcile_patch = patch.object(app_module, "_reconcile", _no_reconcile)
        self._reconcile_patch.start()
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
            self.server.should_exit = True
            self.thread.join(timeout=10)
            self.tmp.cleanup()


_LIVE: _Live | None = None
_UNAVAILABLE = ""


def _live() -> _Live | None:
    """The shared dashboard, or None with a printed reason when this machine
    can't run it. Never raises: a missing browser is a skip, not a failure."""
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
    """Stop the dashboard while the interpreter is still healthy.

    Not atexit: by the time atexit callbacks run, CPython has already banned new
    threads, and uvicorn's loop spawns one on the way out — so an atexit shutdown
    ends in a `can't create new thread at interpreter shutdown` traceback printed
    after the results. pytest calls this hook after the module's tests, and the
    __main__ runner calls it in a finally."""
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
    """Put the page in ``mode`` with that pane's content actually loaded — an
    empty pane passes axe trivially and proves nothing."""
    page.click(f'.act-btn[data-mode="{mode}"]')
    if mode == "runs":
        page.click("#runs-list .row.blocked")
        page.wait_for_selector("form[data-answer] textarea", timeout=10000)
    elif mode in ("files", "diff"):
        page.click(f'.repo-picker[data-picker="{mode}"]')
        page.wait_for_selector("#repo-menu .repo-item", timeout=10000)
        page.click("#repo-menu .repo-item")
        # The trees are `#files-tree` / `#diff-tree`, but the viewers are
        # `#file-view` / `#diff-view` — singular on the files side.
        tree, view = ("files-tree", "file-view") if mode == "files" else ("diff-tree", "diff-view")
        page.wait_for_selector(f"#{tree} .tree-file", timeout=10000)
        page.click(f"#{tree} .tree-file")
        page.wait_for_selector(f"#{view} :not(.fd-empty)", timeout=10000)
    elif mode == "telemetry":
        page.wait_for_selector("#traces-list table.traces tbody tr", timeout=10000)


# --------------------------------------------------------------------------- #
# axe, once per reachable pane
# --------------------------------------------------------------------------- #
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
    # The densest pane and the only one with a form: run rows, the selected run's
    # detail, the markdown question, and the answer textarea + submit.
    _check_mode("runs")


def test_files_pane_is_accessible():
    # Covers the repo combobox/listbox and the disclosure tree, both of which are
    # ARIA-authored widgets rather than native controls.
    _check_mode("files")


def test_diff_pane_is_accessible():
    # diff2html's generated table is third-party markup groom injects — if it
    # regresses accessibility, it does so on groom's page.
    _check_mode("diff")


def test_telemetry_pane_is_accessible():
    _check_mode("telemetry")


def test_settings_pane_is_accessible():
    _check_mode("settings")


# --------------------------------------------------------------------------- #
# Keyboard reachability — what axe cannot see
# --------------------------------------------------------------------------- #
# axe checks the markup's accessibility properties; it does not press Tab. These
# two are the paths an operator has no mouse-free alternative to: choosing a pane
# and answering a gate.
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
        # Operable, not merely focusable: focus one and press Enter, and the pane
        # must actually change — a click-only handler would fail here.
        page.focus('.act-btn[data-mode="telemetry"]')
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.querySelector('.app').dataset.mode === 'telemetry'", timeout=5000)
        pressed = page.get_attribute('.act-btn[data-mode="telemetry"]', "aria-pressed")
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
        # Tab must land on the submit button: the textarea and the button are
        # adjacent in the tab order, so a gate can be answered without a mouse.
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
        # The answer lands in the gate file on disk, and the form clears.
        page.wait_for_function(
            "() => document.querySelector('form[data-answer] textarea')?.value === ''",
            timeout=10000,
        )
    finally:
        page.close()


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
