"""The container supervisor: preflight, and two children with different lifecycles.

`supervisor.py` sits beside the Dockerfile rather than inside the package — it is
harness, not distribution — but it is the process that decides whether an unattended
containerized run survives, so it is tested like engine code.

The load-bearing test is the first one: **the run must be unaffected by the observer**.
groom is optional today (no bind, no sidecar, never fatal) and the supervisor is what
either preserves that or quietly makes groom a hard dependency of every container.

Every child here is a real subprocess, but a trivial one — `sys.executable -c ...`
exiting on command — so nothing waits in real time and nothing hits the network.

    ./.venv/bin/python -m pytest tests/test_supervisor.py
"""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from pathlib import Path

import pytest

import supervisor


def _child(*, code: str, env: dict[str, str] | None = None) -> supervisor.Child:
    return supervisor.Child([sys.executable, "-c", code], env=env or dict(os.environ))


def _exits(rc: int) -> str:
    return f"import sys; sys.exit({rc})"


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# The observer is optional (this is what keeps groom optional)
# --------------------------------------------------------------------------- #


def test_run_completes_with_no_observer_at_all():
    assert _run(supervisor.supervise(_child(code=_exits(0)), None)) == 0


def test_run_exit_code_is_the_containers_with_no_observer():
    assert _run(supervisor.supervise(_child(code=_exits(7)), None)) == 7


def test_observer_that_crashes_immediately_does_not_touch_the_run():
    """A sidecar that cannot even import must cost the run nothing."""
    rc = _run(
        supervisor.supervise(
            _child(code=_exits(1)),                   # the run
            _child(code="raise SystemExit('boom')"),  # the observer
        )
    )
    assert rc == 1


def test_observer_that_outlives_the_run_is_torn_down():
    """The run finishing ends the container; a still-watching observer must not
    hold it open."""
    rc = _run(
        supervisor.supervise(
            _child(code=_exits(0)),
            _child(code="import time; time.sleep(300)"),
            timeout_s=5.0,
        )
    )
    assert rc == 0


def test_missing_observer_binary_is_not_discovered(tmp_path: Path):
    layout = supervisor.Layout(claude_home=tmp_path, observer_src=tmp_path / "absent")
    assert supervisor.install_observer(layout) is None


# --------------------------------------------------------------------------- #
# Observer restart policy
# --------------------------------------------------------------------------- #


def test_only_the_reload_code_restarts_the_observer(tmp_path: Path):
    """Reload is an exit code, not a signal, because a process cannot cleanly
    re-exec from its own imported source. The supervisor is what makes that a
    restart."""
    counter = tmp_path / "starts"
    code = (
        f"import pathlib,sys; p=pathlib.Path({str(counter)!r}); "
        "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); "
        "sys.exit(3 if n < 2 else 0)"
    )
    _run(supervisor.supervise_observer(_child(code=code)))
    assert counter.read_text() == "3"  # two reloads, then a clean exit


def test_a_reload_restages_the_source_before_restarting(tmp_path: Path):
    """The restart has to import a directory written once and complete, not the bind
    the operator may still be saving into. So the refresh happens *between* the exit
    and the restart, not lazily on the next import."""
    counter = tmp_path / "starts"
    order: list[str] = []
    code = (
        f"import pathlib,sys; p=pathlib.Path({str(counter)!r}); "
        "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); "
        "sys.exit(3 if n < 1 else 0)"
    )
    child = _child(code=code)

    def refresh() -> None:
        order.append(f"refresh@{counter.read_text()}")

    _run(supervisor.supervise_observer(child, on_reload=refresh))

    # One reload, and the refresh ran after the first exit and before the second start.
    assert counter.read_text() == "2"
    assert order == ["refresh@1"]


def test_a_refresh_that_raises_still_restarts_on_the_old_generation(tmp_path: Path):
    """livesource keeps the previous generation installed when a refresh fails, so
    the restart has something to run. A raising hook must not end the observer."""
    counter = tmp_path / "starts"
    code = (
        f"import pathlib,sys; p=pathlib.Path({str(counter)!r}); "
        "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); "
        "sys.exit(3 if n < 1 else 0)"
    )

    def boom() -> None:
        raise RuntimeError("staging blew up")

    _run(supervisor.supervise_observer(_child(code=code), on_reload=boom))
    assert counter.read_text() == "2"


def test_a_reload_landing_on_broken_code_fails_safe_instead_of_storming(tmp_path: Path):
    """Any exit that is not the reload code stops the loop for good — otherwise a
    bad edit turns into a restart storm nobody is watching."""
    counter = tmp_path / "starts"
    code = (
        f"import pathlib,sys; p=pathlib.Path({str(counter)!r}); "
        "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); "
        "sys.exit(1)"
    )
    _run(supervisor.supervise_observer(_child(code=code)))
    assert counter.read_text() == "1"


# --------------------------------------------------------------------------- #
# The run's own lifecycle
# --------------------------------------------------------------------------- #


def test_the_run_restarts_on_the_reload_code_with_the_source_restaged(tmp_path: Path):
    """A `--core` reload normally re-execs itself and never reaches here. This is the
    backstop for the case exec cannot serve: an engine that has to be *staged* before it
    exists to run, where exec would re-run the image it is replacing. Same policy as the
    observer's, refresh included."""
    counter = tmp_path / "starts"
    order: list[str] = []
    code = (
        f"import pathlib,sys; p=pathlib.Path({str(counter)!r}); "
        "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); "
        "sys.exit(3 if n < 1 else 0)"
    )

    def refresh() -> None:
        order.append(f"refresh@{counter.read_text()}")

    rc = _run(supervisor.supervise(_child(code=code), None, on_reload=refresh))

    assert rc == 0
    assert counter.read_text() == "2"
    assert order == ["refresh@1"]


def test_a_run_that_fails_after_a_reload_is_not_restarted_again(tmp_path: Path):
    """Only the reserved code restarts, and the code the container reports is the one
    the *last* image exited with — otherwise a reload onto an engine that cannot import
    becomes a storm, and reports success while it storms."""
    counter = tmp_path / "starts"
    code = (
        f"import pathlib,sys; p=pathlib.Path({str(counter)!r}); "
        "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); "
        "sys.exit(3 if n < 1 else 9)"
    )
    assert _run(supervisor.supervise(_child(code=code), None)) == 9
    assert counter.read_text() == "2"


def test_sigterm_reaches_the_run_so_docker_stop_stays_graceful(tmp_path: Path):
    """`docker stop` sends SIGTERM to PID 1; the run is two levels down and only
    gets it because the supervisor forwards it."""
    marker = tmp_path / "term"
    code = (
        "import signal,sys,time,pathlib; "
        f"p=pathlib.Path({str(marker)!r}); "
        "signal.signal(signal.SIGTERM, lambda *_: (p.write_text('term'), sys.exit(9))); "
        "print('up', flush=True); time.sleep(30)"
    )

    async def scenario() -> int:
        run = _child(code=code)
        task = asyncio.create_task(supervisor.supervise(run, None))
        for _ in range(200):  # wait for the spawn, not for a fixed duration
            if run.proc is not None:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.2)
        run.signal(signal.SIGTERM)
        return await task

    assert _run(scenario()) == 9
    assert marker.read_text() == "term"


def test_a_signal_arriving_during_the_spawn_is_not_lost():
    """The window between "decided to start" and "have a pid to signal" is real, and
    a SIGTERM dropped in it would leave the container running after `docker stop`.
    Child re-reads the flag once it has a pid, which is what closes it."""
    child = _child(code="import time; time.sleep(30)")
    child.stopping = True  # as the signal handler would have set it

    async def scenario() -> int:
        proc = await child.start()
        return await proc.wait()

    assert _run(scenario()) != 0  # terminated, not left running


def test_exit_notice_carries_the_code_and_never_changes_it(tmp_path: Path):
    """groom learns the run ended from a one-shot push. It must not be able to alter
    the container's exit status, however it behaves."""
    seen = tmp_path / "notice"
    notice_code = f"import sys,pathlib; pathlib.Path({str(seen)!r}).write_text(sys.argv[-1]); sys.exit(2)"

    rc = _run(
        supervisor.supervise(
            _child(code=_exits(5)),
            None,
            exit_notice=lambda code: [sys.executable, "-c", notice_code, str(code)],
        )
    )
    assert rc == 5
    assert seen.read_text() == "5"


def test_a_wedged_exit_notice_does_not_hold_the_container_open():
    rc = _run(
        supervisor.supervise(
            _child(code=_exits(0)),
            None,
            exit_notice=lambda _: [sys.executable, "-c", "import time; time.sleep(60)"],
            timeout_s=0.5,
        )
    )
    assert rc == 0


# --------------------------------------------------------------------------- #
# Preflight
# --------------------------------------------------------------------------- #


def test_unwritable_mount_fails_here_with_its_own_exit_code(tmp_path: Path):
    """Exit 13, not a confusing failure deep in a workflow node."""
    with pytest.raises(SystemExit) as exc:
        supervisor.require_writable([tmp_path / "never-created"])
    assert exc.value.code == supervisor.NOT_WRITABLE_EXIT_CODE


def test_credentials_already_in_the_volume_win_over_the_host_copy(tmp_path: Path):
    """The CLI rotates its token in-volume; re-seeding from the host would log the
    container out mid-run."""
    home = tmp_path / "state"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / ".credentials.json").write_text("rotated")
    host = tmp_path / "host-creds.json"
    host.write_text("stale")

    supervisor.seed_claude_home(
        supervisor.Layout(claude_home=home, credentials_src=host), {}
    )
    assert (home / ".claude" / ".credentials.json").read_text() == "rotated"


def test_host_credentials_are_seeded_once_into_an_empty_volume(tmp_path: Path):
    home = tmp_path / "state"
    host = tmp_path / "host-creds.json"
    host.write_text("fresh")

    layout = supervisor.Layout(claude_home=home, credentials_src=host)
    supervisor.seed_claude_home(layout, {})

    assert layout.credentials.read_text() == "fresh"
    assert layout.credentials.stat().st_mode & 0o777 == 0o600
    # And the onboarding stub, so a headless run is never prompted.
    assert json.loads(layout.onboarding_stub.read_text())["hasCompletedOnboarding"]


def test_an_explicit_token_beats_both_files(tmp_path: Path):
    home = tmp_path / "state"
    host = tmp_path / "host-creds.json"
    host.write_text("stale")

    layout = supervisor.Layout(claude_home=home, credentials_src=host)
    supervisor.seed_claude_home(layout, {"CLAUDE_CODE_OAUTH_TOKEN": "tok"})
    assert not layout.credentials.exists()


def test_settings_refresh_every_start_because_they_are_config_not_a_secret(tmp_path):
    home = tmp_path / "state"
    settings = tmp_path / "settings.json"
    settings.write_text("v2")
    layout = supervisor.Layout(claude_home=home, settings_src=settings)
    (home / ".claude").mkdir(parents=True)
    (home / ".claude" / "settings.json").write_text("v1")

    supervisor.seed_claude_home(layout, {})
    assert (home / ".claude" / "settings.json").read_text() == "v2"


# --------------------------------------------------------------------------- #
# Environment → arguments (the process boundary)
# --------------------------------------------------------------------------- #


def test_params_come_from_a_generic_prefix_not_a_workflows_vocabulary():
    """workhorse/** must never learn one workflow's field names. The prefix is the
    parameterised primitive: any workflow's params are expressible without this file
    knowing that workflow exists."""
    params = supervisor.run_params(
        {
            "AGENT_PARAM_DOCS_PATH": "/docs",
            "AGENT_PARAM_WORKSPACE_FILE": "/mnt/ws.code-workspace",
            "AGENT_PARAM_EMPTY": "",  # unset, not "explicitly blank"
            "PATH": "/usr/bin",
        }
    )
    assert params == {"docs_path": "/docs", "workspace_file": "/mnt/ws.code-workspace"}


def test_boundary_params_land_in_a_file_so_explicit_params_still_win(tmp_path: Path):
    out = supervisor.write_boundary_params(tmp_path / "p.json", {"docs_path": "/docs"})
    assert json.loads(out.read_text()) == {"docs_path": "/docs"}


def _bin_with(tmp_path: Path, *names: str) -> Path:
    """A venv-like bin/ holding executable stubs for the given console scripts."""
    for name in names:
        script = tmp_path / name
        script.write_text("#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
    return tmp_path


def test_the_run_command_is_the_workflows_own_console_script(tmp_path: Path):
    bin_dir = _bin_with(tmp_path, "workhorse-coder")
    cmd = supervisor.run_command(
        {"WORKFLOW": "coder", "AGENT_RUNS_DIR": "/runs", "AGENT_RUN_ID": "abc"},
        Path("/p.json"),
        ["--params", "story_id=ACME-1"],
        bin_dir=bin_dir,
    )
    # Addressed by path, not by name: the image does not put the venv's bin/ on
    # $PATH, and a bare name silently resolved to nothing.
    assert cmd[:2] == [str(bin_dir / "workhorse-coder"), "run"]
    assert "--runs-dir" in cmd and "/runs" in cmd
    # The run id must be explicit: the digest fallback is identical in every
    # container, so N of them would collide on one run dir.
    assert cmd[cmd.index("--run-id") + 1] == "abc"
    # Trailing operator arguments come last, after --params-file, so they win.
    assert cmd[-2:] == ["--params", "story_id=ACME-1"]


def test_an_unset_workflow_fails_at_spawn_not_mid_run():
    with pytest.raises(SystemExit):
        supervisor.run_command({}, Path("/p.json"), [])


def test_a_workflow_this_image_does_not_carry_fails_at_spawn(tmp_path: Path):
    """A wheel not installed in the image is a workflow the container cannot run.
    Say so here, naming where we looked — not as a resolution error mid-run."""
    with pytest.raises(SystemExit, match="no such workflow: typo"):
        supervisor.run_command(
            {"WORKFLOW": "typo"}, Path("/p.json"), [], bin_dir=_bin_with(tmp_path, "workhorse-coder")
        )


def test_no_run_id_flag_when_the_launcher_minted_none(tmp_path: Path):
    """A hand-started container with no launcher keeps workhorse's own resolution."""
    cmd = supervisor.run_command(
        {"WORKFLOW": "coder"}, Path("/p.json"), [], bin_dir=_bin_with(tmp_path, "workhorse-coder")
    )
    assert "--run-id" not in cmd


def test_checkout_reads_the_workspace_file_from_the_params_not_a_second_variable(
    monkeypatch,
):
    """One source of truth: the run and its checkout cannot disagree about which
    manifest they are using."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        supervisor.workspace,
        "checkout_workspace",
        lambda ws, root, **kw: seen.update({"ws": ws, "root": root, **kw}),
    )
    supervisor.checkout(
        {"WORKSPACE_ROOT": "/workspace", "REPO_URL": "https://example.com/acme.git"},
        {"workspace_file": "/mnt/ws.code-workspace"},
    )
    assert seen["ws"] == "/mnt/ws.code-workspace"
    assert seen["repo_url"] == "https://example.com/acme.git"


def test_the_worktree_choice_crosses_as_an_argument_not_as_environment(monkeypatch):
    """Nothing under the run may read os.environ: a value read there is in no
    checkpoint, so a resume days later silently takes a different one. This process
    is the boundary — it reads the environment once and hands over arguments."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        supervisor.workspace,
        "checkout_workspace",
        lambda ws, root, **kw: seen.update(kw),
    )
    supervisor.checkout(
        {
            "AGENT_SOURCE_MODE": "worktree",
            "AGENT_WORKTREE_ROOT": "/repos/acme/.agents/worktrees/run-1",
            "REPO_URL": "/repos/acme",
        },
        {},
    )
    assert seen["source_mode"] == "worktree"
    assert seen["worktree_root"] == "/repos/acme/.agents/worktrees/run-1"


def test_a_container_with_no_launcher_still_clones(monkeypatch):
    """`clone` stays the default, so driving compose by hand is unchanged."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        supervisor.workspace, "checkout_workspace", lambda ws, root, **kw: seen.update(kw)
    )
    supervisor.checkout({}, {})
    assert seen["source_mode"] == "clone"
    assert seen["worktree_root"] == ""
