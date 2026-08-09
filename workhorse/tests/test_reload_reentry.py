"""What a live reload does to the driver: unwind, re-import, re-enter — same run.

The transport (`workhorse/reload.py`) and the kill (`runner/process.py`) are tested
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
- **A request that could not be cleared stops the run instead of reloading forever.**

Run: uv run python tests/test_reload_reentry.py   (or via pytest)
"""

from __future__ import annotations

import dataclasses
import importlib
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _fakes import RecordingTelemetry  # noqa: E402
from workhorse import otel, reload  # noqa: E402
from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.config_run import RunConfig  # noqa: E402
from workhorse.pyflow import run as run_mod  # noqa: E402
from workhorse.pyflow.driver import drive  # noqa: E402
from workhorse.pyflow.engine import RunEnv  # noqa: E402
from workhorse.pyflow.registry import Registry  # noqa: E402
from workhorse.pyflow.run import RunInvocation, run_pyflow  # noqa: E402
from workhorse.pyflow.transitions import Done, Transition  # noqa: E402
from workhorse.pyflow.workflow import Workflow  # noqa: E402


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
    """`reload.arm(run_dir)` with a guaranteed disarm — the watch is process-wide, so a
    test that left it armed would hand its tmp dir to whatever ran next."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir

    def __enter__(self) -> Path:
        reload.arm(self.run_dir)
        return self.run_dir

    def __exit__(self, *exc: Any) -> None:
        reload.arm(None)


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
        with _Armed(env.run_dir):
            reload.request(env.run_dir, at_boundary=True)
            exc = _raises(reload.ReloadRequested, drive, Quiet(), env)

        assert ran == [], "the state body ran despite an outstanding reload request"
        assert "start" in str(exc), exc
        checkpoint = env.run_dir / ArtifactWriter.CHECKPOINT_FILE
        assert checkpoint.is_file(), "the state was not durable when the reload fired"
        # Left on disk on purpose: `run_pyflow` consumes it, so an unwind that dies on
        # the way out still has the request recording why it started.
        assert reload.pending(env.run_dir) is not None


def test_an_unarmed_run_never_notices_a_request_file():
    """The watch is what scopes a request to a run. An unarmed driver — every other
    test in `tests/` — must pay a single attribute read and nothing else."""

    class Quiet(Workflow):
        def start(self) -> Transition:
            return Done("finished")

    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        reload.request(env.run_dir)
        assert drive(Quiet(), env) == "finished"


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


def _invocation(tmp: str) -> RunInvocation:
    return RunInvocation(
        registry=REGISTRY,
        runs_dir=Path(tmp) / "runs",
        flow="main",
        run_id="t",
        # Forced on with a null adapter: left to auto, the probe would answer from
        # whatever is listening on the dev machine and these tests would pass by
        # environment.
        telemetry=otel.TelemetryHost(
            settings=dataclasses.replace(otel.OtelSettings(), forced=True),
            build=lambda workflow, run_id, run_dir, settings: otel._NullTelemetry(),
        ),
    )


def test_a_run_arms_the_watch_for_its_own_dir_and_disarms_on_the_way_out():
    """Armed after telemetry (so a cut turn's `reload_kill` event has a span to land
    on) and disarmed on every exit path (the watch is process-wide)."""
    seen: list[Path | None] = []

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        seen.append(reload.armed())
        return None

    with tempfile.TemporaryDirectory() as tmp:
        with patch.object(run_mod, "drive", fake_drive):
            assert run_pyflow(_invocation(tmp)) == 0

        assert seen == [Path(tmp) / "runs" / "stub-t"], seen
        assert reload.armed() is None, "the run left the watch armed for the next one"


def test_a_request_that_cannot_be_cleared_stops_the_run_rather_than_looping():
    """The one failure mode a reload must not have. `consume` unlinks before the caller
    acts precisely so this cannot happen; if the unlink silently failed anyway — a
    read-only run dir — the honest outcome is a stop naming the file, not a spin."""

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="Stub", ctx={})
        reload.request(env.run_dir)
        raise reload.ReloadRequested("cut mid-turn")

    # A `consume` that reads the request but leaves it on disk, which is what an
    # unlink that failed looks like from the caller's side.
    def stuck_consume(run_dir: Any) -> reload.ReloadRequest | None:
        return reload.pending(run_dir)

    with tempfile.TemporaryDirectory() as tmp:
        with (
            patch.object(run_mod, "drive", fake_drive),
            patch.object(reload, "consume", stuck_consume),
        ):
            assert run_pyflow(_invocation(tmp)) == 1

    assert reload.armed() is None


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
        run_dir = reload.armed()
        assert run_dir is not None
        (run_dir / "ran-old.txt").write_text(VERSION, encoding="utf-8")
        reload.request(run_dir)
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
        run_dir = reload.armed()
        assert run_dir is not None
        (run_dir / "ran-new.txt").write_text(VERSION, encoding="utf-8")
        return Done(VERSION)


workflow = Registry("probe")
workflow.add_flows(main=Probe)
workflow.entry = Probe
'''


def _write_package(root: Path) -> Any:
    """Materialise the probe distribution under `root` and import its registry."""
    package = root / "reloadable_probe"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "flow.py").write_text(_FLOW_V1, encoding="utf-8")
    (package / "pushed.py").write_text(_FLOW_V2, encoding="utf-8")
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    return importlib.import_module("reloadable_probe.flow").workflow


def _forget_package(root: Path) -> None:
    root_pkg = "reloadable_probe"
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
        assert reload.pending(run_dir) is None
        assert reload.armed() is None
        # And one run dir — a restart would have opened a second.
        assert sorted(p.name for p in (Path(tmp) / "runs").iterdir()) == ["probe-probe"]


if __name__ == "__main__":
    test_a_reload_raised_from_a_state_body_closes_that_states_span()
    test_a_reload_deep_in_a_sub_flow_closes_one_scope_per_drive_frame()
    test_a_boundary_request_is_honoured_after_the_checkpoint_and_before_the_body()
    test_an_unarmed_run_never_notices_a_request_file()
    test_a_run_arms_the_watch_for_its_own_dir_and_disarms_on_the_way_out()
    test_a_request_that_cannot_be_cleared_stops_the_run_rather_than_looping()
    test_a_reload_re_enters_the_same_run_on_the_code_that_was_pushed()
    print("ok")
