"""The run brings up the stack its own book declares, not the first stack another book declares, and stops only what it started."""
from __future__ import annotations

from pathlib import Path

import pytest

from workhorse_workflows.kit.qa import runner
from workhorse_workflows.okf_book.shared import book_run
from workhorse_workflows.okf_book.shared.book_run import (
    StackReadiness,
    run_plan,
    with_app_logs,
)
from workhorse_workflows.okf_book.shared.scenarios import RunSummary, ScenarioOutcome
WEB_STACK = Path("docs/services/web-app/ops/web-app-stack.md")
SERVING = StackReadiness(up=True, serving=True, notes="")

@pytest.fixture
def brought_up(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sources: list[str] = []

    def _bring_up(manifests: list[dict[str, object]], **_kwargs: object) -> list[dict[str, str]]:
        sources.extend(str(manifest.get("source", "")) for manifest in manifests)
        return [{"ready": "yes"}]

    monkeypatch.setattr(runner.runbook, "bring_up_stacks", _bring_up)
    return sources


def _ran(monkeypatch: pytest.MonkeyPatch, message: str) -> None:
    summary = RunSummary(status="failed", scenarios={"create-widget": ScenarioOutcome(status="failed", assertions=1, failures=1, message=message)})

    def _run_scenarios(*_args: object) -> RunSummary:
        return summary

    monkeypatch.setattr(book_run, "run_scenarios", _run_scenarios)


def _app_log(tmp_path: Path) -> str:
    log = tmp_path / "api.log"
    _ = log.write_text(
        "listening on :8080\n"
        "POST /widgets Authorization: Bearer eyJhbGciOi.eyJzdWIi.c2lnbmF0dXJl\n"
        "error cloning the default widget: relation widgets_default does not exist\n",
        encoding="utf-8")
    return str(log)


def test_a_check_the_app_answered_with_a_server_error_shows_the_end_of_its_log_without_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _ran(monkeypatch, "POST http://localhost:8080/widgets returned 500: internal error")
    log = _app_log(tmp_path)

    result = with_app_logs(run_plan(tmp_path, tmp_path / "spec", (), SERVING), (log,))

    assert f"the app answered a server error, and its log {log} ends with:" in result.lines
    assert "  error cloning the default widget: relation widgets_default does not exist" in result.lines
    assert not any("eyJ" in line or "c2lnbmF0dXJl" in line for line in result.lines)


def test_a_check_that_failed_without_a_server_error_leaves_the_log_out(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ran(monkeypatch, "GET http://localhost:8080/widgets returned 404: not found")

    result = with_app_logs(run_plan(tmp_path, tmp_path / "spec", (), SERVING), (_app_log(tmp_path),))

    assert not any("its log" in line for line in result.lines)


def test_a_copy_of_the_app_skips_the_agents_dir_whose_sockets_cannot_be_copied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil
    import socket

    root = tmp_path / "repo"
    (root / ".agents" / "runs" / "okf-book-x").mkdir(parents=True)
    (root / ".agents" / "okf-build").mkdir()
    (root / ".agents" / "okf-build" / "SingletonLock").symlink_to("host-12345")
    _ = (root / "cli.py").write_text("print(1)\n", encoding="utf-8")
    monkeypatch.chdir(root)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.bind(".agents/runs/okf-book-x/control.sock")
        copy = tmp_path / "copy"
        _ = shutil.copytree(root, copy, ignore=book_run.copy_ignored(root))

    assert (copy / "cli.py").is_file()
    assert not (copy / ".agents").exists()
