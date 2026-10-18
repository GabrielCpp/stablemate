from __future__ import annotations

import asyncio
import os
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import _tui_support as support
import pytest
from textual.widgets import OptionList

from groom import state
from groom.models import GateInfo, WorkflowState
from groom.tui.app import GroomTui
from groom.tui.link_ws import WsLink

GATE = "STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\nPick a **storage backend**: postgres or sqlite?\n"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class _Live:
    def __init__(self, base: Path) -> None:
        os.environ["GROOM_DB"] = str(base / "groom.db")

        from groom import app as app_module
        from groom import store

        store.reset()
        self.workspace = base / "ws"
        (self.workspace / "context").mkdir(parents=True)
        self.gate = self.workspace / "context" / "gate.md"
        self.gate.write_text(GATE)
        state.WORKFLOWS.clear()
        state.SCANNING = False
        blocked = state.upsert_workflow(
            support.ACME,
            name="coder-acme",
            workflow_type="coder",
            repo_name="acme",
            current_node="await_operator",
            run_id="run-blocked",
            state=WorkflowState.BLOCKED,
            native=True,
            workspace_volume=str(self.workspace),
        )
        blocked.gates["context/gate.md"] = GateInfo(
            workflow_id=support.ACME, file_path="context/gate.md", question=GATE
        )

        async def _no_reconcile() -> int:
            return 0

        self._patch = patch.object(app_module, "_reconcile", _no_reconcile)
        self._patch.start()

        import uvicorn

        self.port = _free_port()
        config = uvicorn.Config(
            app_module.create_app(), host="127.0.0.1", port=self.port, log_level="error"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)
        self.thread.start()
        self._await_port()

    def _await_port(self, timeout: float = 20.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.05)
        raise RuntimeError("groom did not bind its port")

    def close(self) -> None:
        self._patch.stop()
        self.server.should_exit = True
        self.thread.join(timeout=10)
        state.WORKFLOWS.clear()


@pytest.fixture
def live():
    with tempfile.TemporaryDirectory() as tmp:
        previous = os.environ.get("GROOM_DB")
        server = _Live(Path(tmp))
        try:
            yield server
        finally:
            server.close()
            if previous is None:
                os.environ.pop("GROOM_DB", None)
            else:
                os.environ["GROOM_DB"] = previous


def test_the_real_adapter_answers_a_gate_on_a_real_groom(live: _Live):
    async def scenario() -> None:
        app = GroomTui(WsLink(f"http://127.0.0.1:{live.port}"))
        async with app.run_test(size=(140, 40)) as pilot:
            listing = app.query_one("#runs", OptionList)
            await support.until(lambda: listing.option_count == 1)
            await pilot.press("enter")
            await support.until(lambda: app.pane.blocks())
            await pilot.press("a")
            await pilot.press(*"sqlite")
            await pilot.press("ctrl+s")
            await support.until(lambda: "ANSWERED" in live.gate.read_text())
            text = live.gate.read_text()
            assert text.startswith("STATUS: ANSWERED")
            assert text.rstrip().endswith("sqlite")
            await support.until(lambda: any("Answer sent" in n.message for n in app._notifications))
            await support.until(lambda: not app.pane.blocks())

    asyncio.run(scenario())
