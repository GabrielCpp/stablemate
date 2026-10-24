"""A server that exits partway through a run stops the run and sends its runbook to repair, instead of failing every later scenario on the book."""
from __future__ import annotations

import subprocess

from workhorse_workflows.kit.qa.runner import stack_stopped

WEB_STACK = "docs/services/web-app/ops/web-app-stack.md"

def _exited_group() -> str:
    server = subprocess.Popen(["true"], start_new_session=True)
    _ = server.wait()
    return str(server.pid)


def test_a_group_with_a_running_process_has_not_stopped() -> None:
    server = subprocess.Popen(["sleep", "30"], start_new_session=True)
    try:
        assert stack_stopped((str(server.pid),)) == ""
    finally:
        server.kill()
        _ = server.wait()


def test_a_group_whose_server_exited_has_stopped() -> None:
    pgid = _exited_group()

    assert f"process group {pgid}" in stack_stopped((pgid,))
