"""A stop must be acknowledged, interrupt the run, and leave it resumable."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from workhorse import control, otel, reload
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK
from workhorse.cli import main as cli_main
from workhorse.config_run import AgentResilience
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Done, Transition
from workhorse.pyflow.workflow import Workflow
from workhorse.records import parse_run_record
from workhorse.rundir import find_latest_resumable
from workhorse.runner.process import stream_subprocess


@pytest.mark.parametrize("consume", [reload.cut_requested, reload.boundary_requested])
def test_stop_acknowledges_before_interrupting_at_either_site(
    consume: Callable[[], control.Request | None],
) -> None:
    channel = control.FakeChannel(control.Request(action="stop"))
    control.arm(channel)
    try:
        with pytest.raises(KeyboardInterrupt):
            consume()
        assert channel.replies == [{"ok": True, "action": "stop"}]
        assert channel.pending == []
        assert control.outstanding() is None
    finally:
        control.arm(None)


@pytest.mark.parametrize("reply", [
    {"ok": True, "action": "stop"},
    {"error": "this run does not know the action 'stop'"},
    {},
    {"ok": True},
])
def test_stop_cli_requires_explicit_acceptance_over_the_socket(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], reply: dict[str, object],
) -> None:
    channel = control.SocketChannel.open(tmp_path)

    def serve() -> control.Request:
        request = control.wait_until(
            None, timeout=5, clock=SYSTEM_CLOCK, channel=channel,
        )
        assert request is not None
        channel.reply(reply)
        return request

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            received = pool.submit(serve)
            argv = ["control", "--run", str(tmp_path), "stop"]
            if reply.get("action") == "stop":
                cli_main(argv, workflow="demo", registry=Registry("demo"))
                assert "stop accepted" in capsys.readouterr().out
            else:
                with pytest.raises(SystemExit) as exc:
                    cli_main(argv, workflow="demo", registry=Registry("demo"))
                assert exc.value.code == 1
                output = capsys.readouterr()
                assert "stop accepted" not in output.out
                assert "error:" in output.err
            assert received.result(timeout=2).action == "stop"
    finally:
        channel.close()


def test_stop_of_an_unavailable_run_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc:
        cli_main(
            ["control", "--run", str(tmp_path), "stop"],
            workflow="demo", registry=Registry("demo"),
        )
    assert exc.value.code == 1
    assert "no run is listening" in capsys.readouterr().err


class _Registry(Registry):
    def directory(self) -> Path:
        return Path(__file__).parent


def test_socket_stop_reaps_the_streaming_child_and_preserves_resume(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    run_dir = runs / "stoppable-t"
    replies: list[dict[str, object]] = []
    children: list[int] = []

    class Stoppable(Workflow):
        def start(self) -> Transition:
            with ThreadPoolExecutor(max_workers=1) as pool:
                def on_line(line: str) -> None:
                    children.append(int(line))
                    pool.submit(
                        lambda: replies.append(control.send(run_dir, control.Request(action="stop")))
                    )

                stream_subprocess(
                    [sys.executable, "-u", "-c",
                     "import os, time; print(os.getpid()); time.sleep(30)"],
                    "child", timeout=10, on_line=on_line, resilience=AgentResilience(),
                )
            return Done(None)

    registry = _Registry("stoppable")
    registry.add_flows(main=Stoppable)
    registry.entry = Stoppable
    previous = otel.install(otel.TelemetryHost())
    try:
        with pytest.raises(SystemExit) as exc:
            run_pyflow(RunInvocation(registry=registry, runs_dir=runs, run_id="t"))
        assert exc.value.code == 130
        assert replies == [{"ok": True, "action": "stop"}]
        assert len(children) == 1
        with pytest.raises(ProcessLookupError):
            os.kill(children[0], 0)
        record = parse_run_record((run_dir / "run.json").read_text())
        assert record.interrupted_at
        assert record.terminal is None
        assert find_latest_resumable(runs) == run_dir
        assert "KeyboardInterrupt" in (run_dir / "events.jsonl").read_text()
        assert control.armed().fileno() is None
    finally:
        otel.install(previous)
