"""What a live reload does to the driver: unwind, re-import, re-enter — same run.

The transport (`workhorse/control.py`) and the kill (`runner/process.py`) are tested
next to the code they belong to. What is asserted here is the half that decides whether
a reload is cheap or is indistinguishable from a crash:

- **Every `drive` frame closes its own scope on the way out.** The whole point of the
  feature is that an operator who reloads a broken flow does not pay for it in spans
  that never leave the process — a dangling state span is what makes groom read a
  reload as an abort. `drive` is re-entrant (a `handoff` runs a nested `drive` inside
  its parent's state body), so this has to hold once per level, not once.
- **The boundary request is honoured after the checkpoint, never before.** A state that
  is about to run is already durable, so re-entry replays it having lost nothing.
- **Re-entry is the *same* run.** Same process, same run dir, same root span — a fresh
  generation would be exactly the "restarting looks like a failure" this replaces.

Run: uv run python tests/test_reload_reentry.py   (or via pytest)
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
import sysconfig
import tempfile
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _fakes import FakeBackend, RecordingTelemetry  # noqa: E402
from workhorse._vendor.stablemate_core.config import CONFIG_PATH_ENV  # noqa: E402
from workhorse import control, otel, reload  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.config_run import RunConfig  # noqa: E402
from workhorse.pyflow import run as run_mod  # noqa: E402
from workhorse.pyflow.driver import drive  # noqa: E402
from workhorse.pyflow.engine import RunEnv  # noqa: E402
from workhorse.pyflow.registry import Registry  # noqa: E402
from workhorse.pyflow.run import RunInvocation, run_pyflow  # noqa: E402
from workhorse.pyflow.transitions import Done, Transition  # noqa: E402
from workhorse.pyflow.workflow import Workflow  # noqa: E402
from workhorse.runner import ladder  # noqa: E402


# --------------------------------------------------------------------------- helpers


def _env(tmp: str) -> RunEnv:
    """A run environment rooted in `tmp` — the same shim as test_pyflow's `_env`, cut
    down to what a reload test needs (no agent backend: the turn is never reached)."""
    writer = ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
    )


class _Recording:
    """`RecordingTelemetry` installed for the duration of a `with` block.

    The module-level `otel` functions delegate to whatever host is installed, so this
    puts the previous host back rather than assigning over anything.
    """

    def __enter__(self) -> RecordingTelemetry:
        self.fake = RecordingTelemetry()
        self.previous = otel.install(otel.TelemetryHost(active=self.fake))
        return self.fake

    def __exit__(self, *exc: Any) -> None:
        otel.install(self.previous)


class _Armed:
    """A scripted channel installed with a guaranteed disarm.

    The installed channel is process-wide — one run per process — so a test that left one
    armed would hand its requests to whatever ran next. `FakeChannel` rather than a socket
    because what these tests assert is what the driver *does* with a request, not that a
    kernel delivered it.
    """

    def __init__(self, *requests: control.Request) -> None:
        self.channel = control.FakeChannel(*requests)

    def __enter__(self) -> control.FakeChannel:
        control.arm(self.channel)
        return self.channel

    def __exit__(self, *exc: Any) -> None:
        control.arm(None)


@contextmanager
def _no_config_env() -> Iterator[None]:
    """A re-exec appends `--config` when one is set, and the machine running the tests
    may well have set one. Removing it is what makes an exact-argv assertion an assertion
    about the code rather than about the developer's shell."""
    with patch.dict(run_mod.os.environ):
        run_mod.os.environ.pop(CONFIG_PATH_ENV, None)
        yield


def _raises(exc_type: type[BaseException], fn: Any, *args: Any, **kwargs: Any) -> BaseException:
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")


# ------------------------------------------------------------------- the unwind


def test_a_reload_raised_from_a_state_body_closes_that_states_span():
    """The unclosed-span half of the feature, at its smallest.

    `otel._end_execution` sweeps every span above the one it is closing, so closing the
    state's scope is also what closes the agent node span that never received its `done`
    event — the turn having been cut on purpose.
    """

    class Cut(Workflow):
        def start(self) -> Transition:
            raise reload.ReloadRequested("cut mid-turn")

    with tempfile.TemporaryDirectory() as tmp, _Recording() as fake:
        env = _env(tmp)
        _raises(reload.ReloadRequested, drive, Cut(), env)

        assert [kind for kind, *_ in fake.states] == ["start", "end"], fake.states
        # Closed with no next state: the transition never produced one, and inventing
        # `start` here would say the reload decided something.
        assert fake.states[-1][1:] == ("start", fake.states[0][2], None), fake.states
        # …and closed *marked*. A scope that ended because its work was interrupted is
        # indistinguishable from one that finished if all it exports is two timestamps,
        # and groom's churn rule reads exactly that: unmarked, an operator pushing five
        # fixes into a broken flow pages for the loop the reload was breaking.
        assert fake.cuts == [("start", "reload")], fake.cuts


def test_a_reload_deep_in_a_sub_flow_closes_one_scope_per_drive_frame():
    """`drive` is re-entrant, which is the whole reason the request travels as an
    exception rather than swapping modules where it is noticed. Each frame it passes
    through owes its own close, or the parent's span outlives the run."""

    class Child(Workflow):
        def start(self) -> Transition:
            raise reload.ReloadRequested("cut inside the sub-flow")

    class Parent(Workflow):
        def start(self) -> Transition:
            return Done(self.handoff(Child))

    with tempfile.TemporaryDirectory() as tmp, _Recording() as fake:
        env = _env(tmp)
        _raises(reload.ReloadRequested, drive, Parent(), env)

        kinds = [kind for kind, *_ in fake.states]
        assert kinds == ["start", "start", "end", "end"], fake.states
        # Innermost first: the child's frame closes before the parent's, as an unwind does.
        assert all(entry[3] is None for entry in fake.states if entry[0] == "end"), fake.states


def test_a_boundary_request_is_honoured_after_the_checkpoint_and_before_the_body():
    """The half the stream loop deliberately does not serve: a request that arrived
    while a script node ran, and the `--at-boundary` request it ignores by design.

    The checkpoint for the state about to run is already on disk when this fires, so
    re-entry replays that state with the arguments it was bound with and loses nothing.
    """
    ran: list[str] = []

    class Quiet(Workflow):
        def start(self) -> Transition:
            ran.append("start")
            return Done(None)

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        with _Armed(control.Request(at_boundary=True)) as channel:
            exc = _raises(reload.ReloadRequested, drive, Quiet(), env)

        assert ran == [], "the state body ran despite an outstanding reload request"
        assert "start" in str(exc), exc
        checkpoint = env.run_dir / ArtifactWriter.CHECKPOINT_FILE
        assert checkpoint.is_file(), "the state was not durable when the reload fired"
        # Acknowledged on the way past, so the operator's CLI reports a message that
        # landed rather than one that merely went out.
        assert channel.replies == [{"ok": True, "cut": False}], channel.replies


def test_a_profile_switch_is_applied_in_place_and_the_run_carries_on():
    """The opposite of a reload in the one way that matters: nothing unwinds. The profile
    is re-narrowed every turn, so telling the runner a new name *is* the switch — a
    re-entry would cost the state for a decision the next turn makes anyway."""
    ran: list[str] = []

    class Quiet(Workflow):
        def start(self) -> Transition:
            ran.append("start")
            return Done("finished")

    cfg = {"profiles": {"cheap": {"power": {"high": {"fake": {"model": "haiku"}}}}}}
    with tempfile.TemporaryDirectory() as tmp:
        env = dataclasses.replace(
            _env(tmp), agent_runner=ladder.AgentRunner(backend=FakeBackend(None))
        )
        request = control.Request(action=reload.SWITCH_PROFILE, profile="cheap")
        with (
            _Armed(request) as channel,
            patch("workhorse.runner.ladder.load_config", lambda: cfg),
        ):
            assert drive(Quiet(), env) == "finished"

        assert ran == ["start"], "the switch stopped the run it was only meant to steer"
        runner = env.agent_runner
        assert runner is not None and runner.profile.name == "cheap"
        # Answered here rather than by `reload.py`: this is the frame that knows whether
        # it could be applied, and a refusal reported as a success would leave a week-long
        # run spending on the models nobody chose.
        assert channel.replies == [{"ok": True, "profile": "cheap", "was": ""}]


def test_a_profile_switch_the_run_refuses_is_reported_as_a_refusal():
    class Quiet(Workflow):
        def start(self) -> Transition:
            return Done("finished")

    with tempfile.TemporaryDirectory() as tmp:
        env = dataclasses.replace(
            _env(tmp), agent_runner=ladder.AgentRunner(backend=FakeBackend(None))
        )
        request = control.Request(action=reload.SWITCH_PROFILE, profile="gone")
        with (
            _Armed(request) as channel,
            patch("workhorse.runner.ladder.load_config", lambda: {}),
        ):
            assert drive(Quiet(), env) == "finished"

        runner = env.agent_runner
        assert runner is not None and runner.profile.name == ""
        assert channel.replies and channel.replies[0]["ok"] is False


def test_an_unarmed_run_never_stops_at_a_boundary():
    """The installed channel is what scopes a request to a run. An unarmed driver — every
    other test in `tests/` — must pay a single attribute read and nothing else."""

    class Quiet(Workflow):
        def start(self) -> Transition:
            return Done("finished")

    with tempfile.TemporaryDirectory() as tmp:
        control.arm(None)
        assert drive(Quiet(), _env(tmp)) == "finished"


# -------------------------------------------------------------------- the re-entry


class Stub(Workflow):
    """A one-state flow whose body never runs — `drive` is substituted in the tests
    below. The registry only needs a real class to resolve a directory and instantiate."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    """A registry whose directory is this `tests/` folder — the same shim as
    test_run_terminal.py's. A test module is not a package, so the real `directory()`
    would raise for a reason unrelated to what is under test."""

    def directory(self) -> Path:
        return Path(__file__).parent


def _build_registry() -> Registry:
    registry = _Registry("stub")
    registry.add_flows(main=Stub)
    registry.entry = Stub
    return registry


#: Built once — `add_flows` refuses a second claim on `Stub`.
REGISTRY = _build_registry()


def _invocation(tmp: str, active: Any = None) -> RunInvocation:
    return RunInvocation(
        registry=REGISTRY,
        runs_dir=Path(tmp) / "runs",
        flow="main",
        run_id="t",
        # Forced on with a null adapter unless a test asks for a recording one: left to
        # auto, the probe would answer from whatever is listening on the dev machine and
        # these tests would pass by environment.
        telemetry=otel.TelemetryHost(
            settings=dataclasses.replace(otel.OtelSettings(), forced=True),
            build=lambda workflow, run_id, run_dir, settings: active
            or otel._NullTelemetry(),
        ),
    )


def test_a_run_listens_on_its_own_dir_and_stops_listening_on_the_way_out():
    """Opened after telemetry (so a cut turn's `reload_kill` event has a span to land on)
    and closed on every exit path, because the installed channel is process-wide and a
    socket left bound would make the *next* run in that dir look like a second listener."""
    seen: list[Any] = []

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        channel = control.armed()
        seen.append(getattr(channel, "path", None))
        return None

    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "runs" / "stub-t"
        with patch.object(run_mod, "drive", fake_drive):
            assert run_pyflow(_invocation(tmp)) == 0

        assert seen == [run_dir / control.SOCKET_FILE], seen
        assert control.armed().fileno() is None, "the run left a channel armed"
        assert not (run_dir / control.SOCKET_FILE).exists(), "the socket outlived the run"


def test_a_core_reload_replaces_the_process_only_after_the_run_is_finalized():
    """`--core` cannot be a module swap — `drive`, the ladder and `process.py` are all on
    the stack executing it — so the process image goes instead. What keeps that from
    reading as a crash is the order: the run is stamped `reload`, its spans are closed
    and flushed and the process-wide watch is disarmed, and only *then* is the image
    replaced. `os.execv` runs no `finally` and no `atexit`, so exec'ing a moment earlier
    would drop the run's last spans — the dangling scope a reload exists not to leave."""
    drives = 0
    at_exec: list[tuple[Path, list[str], bool]] = []

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        nonlocal drives
        drives += 1
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="Stub", ctx={})
        raise reload.ReloadRequested("cut mid-turn", core=True)

    fake = RecordingTelemetry()

    def fake_exec(name: str, run_dir: Path, *, cli: str = "", profile: str = "") -> int:
        at_exec.append((run_dir, list(fake.ended), control.armed().fileno() is not None))
        return reload.RELOAD_EXIT_CODE

    with tempfile.TemporaryDirectory() as tmp:
        with (
            patch.object(run_mod, "drive", fake_drive),
            patch.object(run_mod, "_exec_reload", fake_exec),
        ):
            assert run_pyflow(_invocation(tmp, fake)) == reload.RELOAD_EXIT_CODE

        run_dir = Path(tmp) / "runs" / "stub-t"
        assert at_exec == [(run_dir, ["reload"], False)], at_exec

    # Driven once: a `--core` reload does not also swap the workflow package, because
    # the image that comes back re-imports every module from disk anyway.
    assert drives == 1
    # And the reload is on the record as one, naming the state the new image re-enters.
    assert [(name, attrs.get("core"), attrs.get("state")) for name, _, attrs in fake.events] == [
        ("reload", True, "start")
    ], fake.events
    assert control.armed().fileno() is None


def test_the_re_exec_argv_is_the_resume_spelling_not_the_original_one():
    """The original argv is not replayed: its `--param`/`--params-file` are already in
    the checkpoint the new image resumes from, so replaying them would let a file the
    operator edited meanwhile win over what the run actually holds.

    An exec that cannot happen at all exits with the reserved reload code, which is a
    restart under a supervisor and a resumable stop without one — never a silent
    carry-on against the code the operator asked to replace."""
    calls: list[tuple[str, list[str]]] = []

    def fake_execv(path: str, argv: list[str]) -> None:
        calls.append((path, list(argv)))
        raise OSError("the console script moved")

    # A path that does not exist, so `shutil.which` is deterministic rather than
    # answering from whatever this machine has on PATH.
    script = "/nonexistent/bin/workhorse-stub"
    with (
        patch.object(run_mod.os, "execv", fake_execv),
        patch.object(run_mod.sys, "argv", [script, "run", "--param", "story=4"]),
        _no_config_env(),
    ):
        rc = run_mod._exec_reload("stub", Path("/runs/stub-t"))

    assert rc == reload.RELOAD_EXIT_CODE
    assert calls == [(script, [script, "run", "--resume-run", "/runs/stub-t"])], calls


def test_moving_a_run_onto_another_cli_re_execs_naming_it():
    """The one thing a resume cannot read off the checkpoint. `--cli` is resolved at the
    process edge (`cli/run.py`) and never stored, so a run told to change agent CLI has to
    say which one in the argv it comes back on — the inherited environment still names the
    one it started on. Everything else stays the resume spelling, because everything else
    *is* in the checkpoint."""
    calls: list[list[str]] = []

    def fake_execv(path: str, argv: list[str]) -> None:
        calls.append(list(argv))
        raise OSError("no such image")

    script = "/nonexistent/bin/workhorse-stub"
    with (
        patch.object(run_mod.os, "execv", fake_execv),
        patch.object(run_mod.sys, "argv", [script, "run", "--cli", "opencode"]),
        _no_config_env(),
    ):
        run_mod._exec_reload("stub", Path("/runs/stub-t"), cli="claude")

    assert calls == [
        [script, "run", "--resume-run", "/runs/stub-t", "--cli", "claude"]
    ], calls


def test_a_re_exec_builds_its_argv_with_the_same_function_the_launch_record_does():
    """The two are the same claim about the same run — this process's re-exec line and
    the line a supervisor re-spawns off `launch.json` — and they were one copy-paste
    away from disagreeing. A second builder is how a resume ends up landing on the wrong
    profile, or on a `--no-cache` that deletes the run it was resuming."""
    calls: list[tuple] = []

    def fake_builder(program, run_dir, **kwargs):
        calls.append((program, run_dir, kwargs))
        return [program, "run", "--resume-run", str(run_dir)]

    def fake_execv(path: str, argv: list[str]) -> None:
        raise OSError("no such image")

    script = "/nonexistent/bin/workhorse-stub"
    with (
        patch.object(run_mod, "resume_argv", fake_builder),
        patch.object(run_mod.os, "execv", fake_execv),
        patch.object(run_mod.sys, "argv", [script, "run"]),
        _no_config_env(),
    ):
        run_mod._exec_reload("stub", Path("/runs/stub-t"), cli="claude", profile="cheap")

    assert calls == [(script, Path("/runs/stub-t"),
                      {"cli": "claude", "profile": "cheap", "config_path": ""})], calls


def test_a_re_exec_carries_the_live_profile_and_the_config_file_it_is_reading():
    """Two things the resume would otherwise get wrong. The profile, because
    `switch-profile` applies in-process and `run.json` still names the one the run was
    launched with — so with no flag the new image would resolve from the profile the
    operator switched *away* from. The config file, because a re-exec that does not say
    which one it is on is the one nobody can diagnose from the line they have."""
    calls: list[list[str]] = []

    def fake_execv(path: str, argv: list[str]) -> None:
        calls.append(list(argv))
        raise OSError("no such image")

    script = "/nonexistent/bin/workhorse-stub"
    with (
        patch.object(run_mod.os, "execv", fake_execv),
        patch.object(run_mod.sys, "argv", [script, "run"]),
        patch.dict(run_mod.os.environ, {CONFIG_PATH_ENV: "/etc/stablemate.toml"}),
    ):
        run_mod._exec_reload("stub", Path("/runs/stub-t"), profile="cheap")

    assert calls == [[
        script, "run", "--resume-run", "/runs/stub-t",
        "--profile", "cheap", "--config", "/etc/stablemate.toml",
    ]], calls


def test_a_switch_is_a_core_reload_even_when_nobody_asked_for_one():
    """A request naming a CLI implies the process image, whatever its `core` flag says.
    The backend is bound once at the edge and handed to the run, so re-importing the
    workflow package — all a tier-1 reload does — could not move a live run onto another
    agent CLI however plainly the request asked for it. Honouring it halfway would be the
    worst of the three outcomes: an operator told the switch happened, on a run still
    spending on the CLI they were moving off."""
    at_exec: list[tuple[Path, str]] = []

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="Stub", ctx={})
        raise reload.ReloadRequested("switch requested", core=False, cli="claude")

    def fake_exec(name: str, run_dir: Path, *, cli: str = "", profile: str = "") -> int:
        at_exec.append((run_dir, cli))
        return reload.RELOAD_EXIT_CODE

    fake = RecordingTelemetry()
    with tempfile.TemporaryDirectory() as tmp:
        with (
            patch.object(run_mod, "drive", fake_drive),
            patch.object(run_mod, "_exec_reload", fake_exec),
        ):
            assert run_pyflow(_invocation(tmp, fake)) == reload.RELOAD_EXIT_CODE
        assert at_exec == [(Path(tmp) / "runs" / "stub-t", "claude")], at_exec

    # And the switch is on the record as one, so a run that came back on another CLI can
    # be told apart later from one that merely reloaded.
    assert [(attrs.get("core"), attrs.get("cli")) for _, _, attrs in fake.events] == [
        (True, "claude")
    ], fake.events


# ------------------------------------------------------- the re-import, for real

#: The workflow package the re-entry test reloads. Written to disk rather than
#: monkeypatched, because what is under test is `sys.modules` being purged and the
#: module re-read from a file that changed underneath a running process — the one thing
#: an in-memory double cannot stand in for.
_FLOW_V1 = '''
"""The broken flow. It pushes the fix over itself, then asks to be reloaded."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workhorse import reload
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.transitions import Done
from workhorse.pyflow.workflow import Workflow

VERSION = "old"


class Probe(Workflow):
    def start(self) -> Any:
        here = Path(__file__)
        # The operator's push, standing in for a `git pull`.
        (here.parent / "pushed.py").replace(here)
        (self.run_dir / "ran-old.txt").write_text(VERSION, encoding="utf-8")
        raise reload.ReloadRequested("the operator cut this turn")

    def unused(self) -> Any:
        return Done(None)


workflow = Registry("probe")
workflow.add_flows(main=Probe)
workflow.entry = Probe
'''

_FLOW_V2 = '''
"""The pushed fix. Same state name, so the checkpoint still resolves."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workhorse import reload
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.transitions import Done
from workhorse.pyflow.workflow import Workflow

VERSION = "new"


class Probe(Workflow):
    def start(self) -> Any:
        (self.run_dir / "ran-new.txt").write_text(VERSION, encoding="utf-8")
        return Done(VERSION)


workflow = Registry("probe")
workflow.add_flows(main=Probe)
workflow.entry = Probe
'''


#: A library the workflow imports and the operator fixes — the shape of every real
#: workflow, which is several distributions deep rather than one package. The flow below
#: branches on this value instead of pushing a new copy of itself, so what the assertion
#: proves is specifically that the *dependency* was re-read.
#: The two payloads differ in *length*, not just in bytes. CPython validates a cached
#: `.pyc` against its source's mtime **and size**, both at one-second granularity, so a
#: same-second rewrite of exactly the same length would be served from the stale cache
#: and this test would measure the bytecode cache rather than the reload. A real push
#: lands hours after the import it replaces; a test rewrites the file microseconds after.
_VERSION_V2 = "new-and-longer"
_LIB_V1 = 'VERSION = "old"\n'
_LIB_V2 = f'VERSION = "{_VERSION_V2}"\n'

_FLOW_OVER_LIB = '''
"""A flow whose defect is in the library it calls, not in itself."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from probe_lib import value

from workhorse import reload
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.transitions import Done
from workhorse.pyflow.workflow import Workflow


class Probe(Workflow):
    def start(self) -> Any:
        if value.VERSION != "old":
            (self.run_dir / "ran-new.txt").write_text(value.VERSION, encoding="utf-8")
            return Done(value.VERSION)
        # The operator's push — into the library, with this package left untouched.
        Path(value.__file__).write_text(@V2@, encoding="utf-8")
        (self.run_dir / "ran-old.txt").write_text(value.VERSION, encoding="utf-8")
        raise reload.ReloadRequested("the operator cut this turn")


workflow = Registry("probe")
workflow.add_flows(main=Probe)
workflow.entry = Probe
'''.replace("@V2@", repr(_LIB_V2))


def _write_package(root: Path, flow: str = _FLOW_V1) -> Any:
    """Materialise the probe distribution under `root` and import its registry."""
    package = root / "reloadable_probe"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "flow.py").write_text(flow, encoding="utf-8")
    (package / "pushed.py").write_text(_FLOW_V2, encoding="utf-8")
    lib = root / "probe_lib"
    lib.mkdir()
    (lib / "__init__.py").write_text("", encoding="utf-8")
    (lib / "value.py").write_text(_LIB_V1, encoding="utf-8")
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    return importlib.import_module("reloadable_probe.flow").workflow


def _forget_package(root: Path) -> None:
    for root_pkg in ("reloadable_probe", "probe_lib"):
        for name in [m for m in sys.modules if m == root_pkg or m.startswith(root_pkg + ".")]:
            del sys.modules[name]
    if str(root) in sys.path:
        sys.path.remove(str(root))


def test_a_reload_re_enters_the_same_run_on_the_code_that_was_pushed():
    """The feature, end to end and with nothing about it faked.

    A run stops mid-state on a request, the workflow package is purged and re-read from
    disk, and the run re-enters *its own* checkpoint — same process, same run dir, same
    root span. That last part is the point: a restart would be a new generation, which
    is what makes a reload read as a failure in groom.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "src"
        registry = _write_package(root)
        try:
            code = run_pyflow(
                dataclasses.replace(_invocation(tmp), registry=registry, run_id="probe")
            )
        finally:
            _forget_package(root)

        run_dir = Path(tmp) / "runs" / "probe-probe"
        assert code == 0, code
        assert (run_dir / "ran-old.txt").read_text(encoding="utf-8") == "old"
        # The proof of re-entry: the *second* pass ran, and it ran the pushed class.
        assert (run_dir / "ran-new.txt").read_text(encoding="utf-8") == "new"
        # One request, one reload.
        assert control.armed().fileno() is None
        # And one run dir — a restart would have opened a second.
        assert sorted(p.name for p in (Path(tmp) / "runs").iterdir()) == ["probe-probe"]


def test_a_reload_picks_up_a_fix_to_a_library_the_workflow_imports():
    """The failure this scope exists to prevent, stated as the operator meets it.

    A workflow is several distributions deep — the state machine calls a doc-graph
    validator, a shared kit — and a defect is at least as likely to be in one of those as
    in the flow. Purging only the entry package would leave the fixed library in
    `sys.modules`, re-import the workflow against the stale copy, and log a successful
    reload over code that did not change: a false receipt, which is worse than the no-op
    it hides, because the operator stops looking. Here the flow is byte-identical across
    the reload and only the library moved.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "src"
        registry = _write_package(root, flow=_FLOW_OVER_LIB)
        try:
            code = run_pyflow(
                dataclasses.replace(_invocation(tmp), registry=registry, run_id="lib")
            )
        finally:
            _forget_package(root)

        run_dir = Path(tmp) / "runs" / "probe-lib"
        assert code == 0, code
        assert (run_dir / "ran-old.txt").read_text(encoding="utf-8") == "old"
        assert (run_dir / "ran-new.txt").read_text(encoding="utf-8") == _VERSION_V2


def test_the_environment_is_kept_while_the_working_tree_is_replaced():
    """The safety invariant, stated over the scan rather than over one reload.

    Replacing a package the *engine* also holds would hand objects of the new classes to
    the surviving frames' old ones — the failure that makes a hot reload unpredictable
    rather than merely incomplete. Site-packages is the line: workhorse's own
    dependencies live there, and so nothing an operator can edit in place does.
    """
    site = Path(sysconfig.get_paths()["purelib"])
    tree = Path("/srv/checkout")
    fakes = {
        # A wheel-installed dependency the engine may also be holding: kept.
        "vendored_dep": site / "vendored_dep" / "__init__.py",
        "vendored_dep.sub": site / "vendored_dep" / "sub.py",
        # An editable sibling — `__file__` points at the source tree, never at the `.pth`
        # shim — so it is the operator's to fix, and a reload's to replace.
        "probe_sibling": tree / "probe_sibling" / "__init__.py",
        # A namespace package: nothing on disk to have been fixed.
        "probe_namespace": None,
    }
    saved = {name: sys.modules.get(name) for name in fakes}
    for name, origin in fakes.items():
        module = types.ModuleType(name)
        if origin is not None:
            module.__file__ = str(origin)
        sys.modules[name] = module
    try:
        roots = run_mod._reloadable_roots("reloadable_probe.flow")
    finally:
        for name, previous in saved.items():
            if previous is None:
                del sys.modules[name]
            else:
                sys.modules[name] = previous

    # The entry package first and unconditionally: a workflow installed as a wheel — the
    # docker image, where nothing is a source tree — still reloads exactly as before.
    assert roots[0] == "reloadable_probe"
    assert "probe_sibling" in roots
    assert "vendored_dep" not in roots
    assert "probe_namespace" not in roots
    # The engine's own modules are on the stack doing the reload; `--core` is for those.
    assert "workhorse" not in roots
    assert not {"sys", "json", "pathlib", "__main__"} & set(roots)


if __name__ == "__main__":
    test_a_reload_raised_from_a_state_body_closes_that_states_span()
    test_a_reload_deep_in_a_sub_flow_closes_one_scope_per_drive_frame()
    test_a_boundary_request_is_honoured_after_the_checkpoint_and_before_the_body()
    test_an_unarmed_run_never_stops_at_a_boundary()
    test_a_run_listens_on_its_own_dir_and_stops_listening_on_the_way_out()
    test_a_core_reload_replaces_the_process_only_after_the_run_is_finalized()
    test_the_re_exec_argv_is_the_resume_spelling_not_the_original_one()
    test_moving_a_run_onto_another_cli_re_execs_naming_it()
    test_a_switch_is_a_core_reload_even_when_nobody_asked_for_one()
    test_a_reload_re_enters_the_same_run_on_the_code_that_was_pushed()
    test_a_reload_picks_up_a_fix_to_a_library_the_workflow_imports()
    test_the_environment_is_kept_while_the_working_tree_is_replaced()
    print("ok")
