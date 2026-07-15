"""Tests for groom.sidecar: inotify-event -> push translation, and the
fire-and-forget/silent-on-failure discipline that is the sidecar's core
safety property (a container with no groom listening must behave exactly as
it does today). The real inotify_simple.INotify is never exercised here —
only the pure functions that decide what to do with an already-received
Event, plus _push()'s HTTP-call wrapping.

Run: uv run python tests/test_sidecar.py   (or via pytest)
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from groom import cli, sidecar
from inotify_simple import flags


def _event(wd, mask, name=""):
    return SimpleNamespace(wd=wd, mask=mask, cookie=0, name=name)


def test_push_progress_posts_expected_shape():
    captured = {}

    class _FakeResponse:
        def close(self):
            pass

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _FakeResponse()

    with patch.object(sidecar.urllib.request, "urlopen", _fake_urlopen), \
         patch.dict(sidecar.os.environ, {"REPO_NAME": "Acme", "REPO_BRANCH": "fixes/x"}, clear=False):
        sidecar.push_progress("resolve_integrity")

    assert captured["url"] == f"http://{sidecar.GROOM_HOST}:{sidecar.GROOM_PORT}/push/progress"
    assert captured["body"]["current_node"] == "resolve_integrity"
    assert captured["body"]["repo_name"] == "Acme"
    assert captured["body"]["repo_branch"] == "fixes/x"
    assert "container_id" in captured["body"]


def test_push_blocked_posts_expected_shape():
    captured = {}

    class _FakeResponse:
        def close(self):
            pass

    def _fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse()

    with patch.object(sidecar.urllib.request, "urlopen", _fake_urlopen):
        sidecar.push_blocked("docs/gate.md", "Which default?")

    assert captured["body"]["file_path"] == "docs/gate.md"
    assert captured["body"]["question"] == "Which default?"


def test_push_exited_posts_expected_shape():
    captured = {}

    class _FakeResponse:
        def close(self):
            pass

    def _fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse()

    with patch.object(sidecar.urllib.request, "urlopen", _fake_urlopen):
        sidecar.push_exited(3)

    assert captured["url"] == f"http://{sidecar.GROOM_HOST}:{sidecar.GROOM_PORT}/push/exited"
    assert captured["body"]["exit_code"] == 3
    assert "container_id" in captured["body"]


def test_push_exited_is_silent_when_groom_is_unreachable():
    def _raise(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    with patch.object(sidecar.urllib.request, "urlopen", _raise):
        sidecar.push_exited(0)  # must not raise


def test_push_is_silent_when_groom_is_unreachable():
    def _raise(*args, **kwargs):
        raise urllib.error.URLError("connection refused")

    with patch.object(sidecar.urllib.request, "urlopen", _raise):
        # Must not raise — this is the whole safety property of the sidecar.
        sidecar.push_progress("some_node")
        sidecar.push_blocked("docs/gate.md", "question?")


def test_push_is_silent_on_any_unexpected_exception():
    def _raise(*args, **kwargs):
        raise ValueError("something else broke")

    with patch.object(sidecar.urllib.request, "urlopen", _raise):
        sidecar.push_progress("some_node")


def test_handle_event_under_runs_triggers_progress_push():
    wd_to_path = {1: "/runs/run-20260705-090000"}
    pushed = {}

    def _fake_current_node():
        return "resolve_integrity"

    def _fake_push_progress(node):
        pushed["node"] = node

    event = _event(1, flags.CLOSE_WRITE, name="events.jsonl")
    with patch.object(sidecar, "RUNS_DIR", sidecar.Path("/runs")), \
         patch.object(sidecar, "_current_node", _fake_current_node), \
         patch.object(sidecar, "push_progress", _fake_push_progress):
        sidecar._handle_event(None, event, wd_to_path)

    assert pushed["node"] == "resolve_integrity"


def test_handle_event_on_awaiting_gate_triggers_blocked_push():
    wd_to_path = {2: "/workspace/docs/epics/fixes"}
    pushed = {}

    def _fake_push_blocked(rel_path, question):
        pushed["rel_path"] = rel_path
        pushed["question"] = question

    gate_text = "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nWhich default?\n"
    event = _event(2, flags.CLOSE_WRITE, name="gate.md")

    with patch.object(sidecar, "WORKSPACE_DIR", sidecar.Path("/workspace")), \
         patch.object(sidecar, "RUNS_DIR", sidecar.Path("/runs")), \
         patch.object(sidecar.Path, "read_text", lambda self: gate_text), \
         patch.object(sidecar, "push_blocked", _fake_push_blocked):
        sidecar._handle_event(None, event, wd_to_path)

    assert pushed["rel_path"] == "docs/epics/fixes/gate.md"
    assert pushed["question"] == "Which default?"


def test_handle_event_ignores_files_not_awaiting():
    pushed = []
    wd_to_path = {2: "/workspace/docs"}
    event = _event(2, flags.MODIFY, name="notes.md")

    with patch.object(sidecar, "WORKSPACE_DIR", sidecar.Path("/workspace")), \
         patch.object(sidecar, "RUNS_DIR", sidecar.Path("/runs")), \
         patch.object(sidecar.Path, "read_text", lambda self: "STATUS: CONSUMED\n"), \
         patch.object(sidecar, "push_blocked", lambda *a: pushed.append(a)):
        sidecar._handle_event(None, event, wd_to_path)

    assert pushed == []


def test_handle_event_ignores_unknown_watch_descriptor():
    # No exception, no push, when the wd isn't in our map (e.g. a stale watch).
    with patch.object(sidecar, "push_progress", side_effect=AssertionError("should not push")):
        sidecar._handle_event(None, _event(999, flags.MODIFY, name="x"), {})


# --------------------------------------------------------------------------- #
# Pull-side query: scan_gates / _terminal / snapshot / cli --query
# --------------------------------------------------------------------------- #
def test_scan_gates_finds_awaiting_and_skips_git_and_non_awaiting():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "docs").mkdir()
        (ws / "docs" / "gate.md").write_text(
            "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nWhich default?\n"
        )
        (ws / "docs" / "done.md").write_text("STATUS: CONSUMED\n\nnothing to see\n")
        (ws / ".git").mkdir()
        (ws / ".git" / "hook.md").write_text("STATUS: AWAITING_OPERATOR\n")  # excluded dir
        with patch.object(sidecar, "WORKSPACE_DIR", ws):
            gates = sidecar.scan_gates()
    assert gates == [{"file_path": "docs/gate.md", "question": "Which default?"}]


def test_terminal_reads_latest_run_json():
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp)
        rd = runs / "coder-20260101-000000"
        rd.mkdir()
        (rd / "run.json").write_text('{"terminal": "done"}')
        with patch.object(sidecar, "RUNS_DIR", runs):
            assert sidecar._terminal() == "done"


def test_snapshot_reports_node_terminal_and_gates():
    with tempfile.TemporaryDirectory() as tmp_ws, tempfile.TemporaryDirectory() as tmp_runs:
        ws, runs = Path(tmp_ws), Path(tmp_runs)
        (ws / "context.md").write_text(
            "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nPick one?\n"
        )
        rd = runs / "coder-20260101-000000"
        rd.mkdir()
        (rd / "checkpoint.json").write_text('{"current_id": "await_operator"}')
        (rd / "run.json").write_text('{"terminal": ""}')
        with patch.object(sidecar, "WORKSPACE_DIR", ws), patch.object(sidecar, "RUNS_DIR", runs):
            snap = sidecar.snapshot()
    assert snap["current_node"] == "await_operator"
    assert snap["terminal"] == ""
    assert snap["gates"] == [{"file_path": "context.md", "question": "Pick one?"}]


def test_cli_query_prints_snapshot_json_and_does_not_watch():
    fake = {"current_node": "n1", "terminal": "", "gates": []}
    buf = io.StringIO()
    with patch.object(sidecar, "snapshot", return_value=fake), \
         patch.object(sidecar, "run", side_effect=AssertionError("--query must not start the watch loop")), \
         contextlib.redirect_stdout(buf):
        cli.sidecar_main(["--query"])
    assert json.loads(buf.getvalue()) == fake


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)
