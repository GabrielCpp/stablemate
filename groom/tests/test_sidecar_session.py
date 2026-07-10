"""Tests for the persistent-session half of groom.sidecar: the data-plane RPC
handlers (getTree/getFile/getDiff + the traversal guard), the hello advertise,
the event→frame classifier, and the reload → exit-code-3 path. No real
WebSocket or groom is involved — a fake socket captures/feeds frames.

Run: uv run python tests/test_sidecar_session.py   (or via pytest)
"""
from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from groom import cli, sidecar
from inotify_simple import flags


# --------------------------------------------------------------------------- #
# Data-plane RPC handlers (local-disk reads with the traversal guard)
# --------------------------------------------------------------------------- #
def test_safe_relpath_accepts_normal_and_rejects_traversal():
    assert sidecar._safe_relpath("predykt/src/a.py") == "predykt/src/a.py"
    for bad in ("/etc/passwd", "../x", "a/../../b", "", "a/../b"):
        try:
            sidecar._safe_relpath(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_rpc_get_tree_lists_files_skipping_vendor_dirs():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        repo = ws / "predykt"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.py").write_text("x")
        (repo / "README.md").write_text("y")
        (repo / ".git").mkdir()
        (repo / ".git" / "cfg").write_text("z")  # excluded dir
        with patch.object(sidecar, "WORKSPACE_DIR", ws):
            out = sidecar._rpc_get_tree({"repo": "predykt"})
    assert out == {"paths": ["README.md", "src/a.py"]}


def test_rpc_get_file_reads_local_file():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "predykt").mkdir()
        (ws / "predykt" / "a.py").write_text("print(1)\n")
        with patch.object(sidecar, "WORKSPACE_DIR", ws):
            out = sidecar._rpc_get_file({"repo": "predykt", "path": "a.py"})
    assert out == {"content": "print(1)\n"}


def test_rpc_get_file_rejects_traversal():
    try:
        sidecar._rpc_get_file({"repo": "predykt", "path": "../../etc/passwd"})
    except ValueError:
        return
    raise AssertionError("expected ValueError on a traversal path")


def test_git_diff_reports_working_tree_changes():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        repo = ws / "app"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        (repo / "f.txt").write_text("one\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)
        (repo / "f.txt").write_text("two\n")
        with patch.object(sidecar, "WORKSPACE_DIR", ws):
            out = sidecar._rpc_get_diff({"repo": "app"})
    assert "-one" in out["diff"] and "+two" in out["diff"]


def test_git_diff_empty_when_no_repo():
    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(sidecar, "WORKSPACE_DIR", Path(tmp)):
            assert sidecar._rpc_get_diff({"repo": ""}) == {"diff": ""}


# --------------------------------------------------------------------------- #
# _handle_rpc: dispatch + reply framing
# --------------------------------------------------------------------------- #
class _FakeWS:
    def __init__(self, incoming=()):
        self.sent: list[dict] = []
        self._incoming = list(incoming)

    async def send(self, text):
        self.sent.append(json.loads(text))

    def __aiter__(self):
        async def _gen():
            for msg in self._incoming:
                yield json.dumps(msg)

        return _gen()

    async def close(self):
        pass


def test_handle_rpc_get_tree_replies_ok():
    with tempfile.TemporaryDirectory() as tmp:
        ws_dir = Path(tmp)
        (ws_dir / "a.py").write_text("x")
        sock = _FakeWS()
        with patch.object(sidecar, "WORKSPACE_DIR", ws_dir):
            asyncio.run(sidecar._handle_rpc(sock, {"type": "rpc", "id": "9", "method": "getTree", "params": {}}))
    assert sock.sent == [{"type": "rpc_result", "id": "9", "ok": True, "data": {"paths": ["a.py"]}}]


def test_handle_rpc_unknown_method_replies_error():
    sock = _FakeWS()
    asyncio.run(sidecar._handle_rpc(sock, {"type": "rpc", "id": "1", "method": "getBogus", "params": {}}))
    assert sock.sent[0]["ok"] is False
    assert "getBogus" in sock.sent[0]["error"]


def test_handle_rpc_get_file_traversal_replies_error():
    sock = _FakeWS()
    asyncio.run(sidecar._handle_rpc(sock, {"type": "rpc", "id": "2", "method": "getFile", "params": {"path": "../x"}}))
    assert sock.sent[0]["ok"] is False
    assert "unsafe" in sock.sent[0]["error"]


# --------------------------------------------------------------------------- #
# hello advertise + event classifier
# --------------------------------------------------------------------------- #
def test_hello_frame_carries_identity_and_snapshot():
    with patch.object(sidecar, "snapshot", return_value={"current_node": "n1", "terminal": "", "gates": []}), \
         patch.dict(sidecar.os.environ, {"REPO_NAME": "Predykt", "REPO_BRANCH": "main"}, clear=False):
        frame = sidecar._hello_frame()
    assert frame["type"] == "hello"
    assert frame["identity"]["repo_name"] == "Predykt"
    assert frame["snapshot"]["current_node"] == "n1"


def _event(wd, mask, name=""):
    return SimpleNamespace(wd=wd, mask=mask, cookie=0, name=name)


def test_classify_event_runs_write_is_progress():
    wd_to_path = {1: "/runs/run-1"}
    with patch.object(sidecar, "RUNS_DIR", Path("/runs")), \
         patch.object(sidecar, "_current_node", lambda: "resolve"):
        frame = sidecar._classify_event(_event(1, flags.CLOSE_WRITE, name="events.jsonl"), wd_to_path)
    assert frame == {"type": "progress", "current_node": "resolve"}


def test_classify_event_awaiting_gate_is_blocked():
    wd_to_path = {2: "/workspace/docs"}
    gate = "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nWhich default?\n"
    with patch.object(sidecar, "WORKSPACE_DIR", Path("/workspace")), \
         patch.object(sidecar, "RUNS_DIR", Path("/runs")), \
         patch.object(sidecar.Path, "read_text", lambda self: gate):
        frame = sidecar._classify_event(_event(2, flags.CLOSE_WRITE, name="gate.md"), wd_to_path)
    assert frame == {"type": "blocked", "file_path": "docs/gate.md", "question": "Which default?"}


def test_classify_event_ignores_unknown_wd():
    assert sidecar._classify_event(_event(999, flags.MODIFY, name="x"), {}) is None


# --------------------------------------------------------------------------- #
# reload → exit code 3
# --------------------------------------------------------------------------- #
def test_run_session_advertises_hello_then_reload_raises():
    sock = _FakeWS(incoming=[{"type": "reload"}])
    missing = Path("/nonexistent-groom-test-xyz")
    with patch.object(sidecar, "WORKSPACE_DIR", missing), \
         patch.object(sidecar, "RUNS_DIR", missing), \
         patch.object(sidecar, "snapshot", return_value={"current_node": "", "terminal": "", "gates": []}):
        try:
            asyncio.run(sidecar._run_session(sock))
        except sidecar.ReloadRequested:
            pass
        else:
            raise AssertionError("expected ReloadRequested from a reload frame")
    assert sock.sent[0]["type"] == "hello"


def test_serve_returns_reload_code_when_session_requests_reload():
    def _fake_connect(uri):
        class _AsyncIter:
            def __aiter__(self):
                async def _gen():
                    yield _FakeWS()

                return _gen()

        return _AsyncIter()

    async def _reload_session(ws):
        raise sidecar.ReloadRequested

    with patch.object(sidecar, "connect", _fake_connect), \
         patch.object(sidecar, "_run_session", _reload_session):
        code = asyncio.run(sidecar._serve())
    assert code == sidecar.RELOAD_EXIT_CODE


def test_run_maps_reload_code_to_systemexit():
    async def _fake_serve():
        return sidecar.RELOAD_EXIT_CODE

    with patch.object(sidecar, "_serve", _fake_serve):
        try:
            sidecar.run()
        except SystemExit as exc:
            assert exc.code == sidecar.RELOAD_EXIT_CODE
            return
    raise AssertionError("expected SystemExit(3)")


def test_cli_sidecar_default_runs_session():
    called = {}
    with patch.object(sidecar, "run", lambda: called.setdefault("ran", True)):
        cli.sidecar_main([])
    assert called.get("ran") is True


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
