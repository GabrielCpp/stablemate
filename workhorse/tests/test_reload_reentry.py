"""What a live reload does to the driver: unwind, re-import, re-enter — same run."""

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




def _env(tmp: str) -> RunEnv:
    """A run environment rooted in `tmp` — the same shim as test_pyflow's `_env`, cut down to what a reload test needs (no agent backend: the turn is never reached)."""
    writer = ArtifactWriter("acme", Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
    )


class _Recording:
    """`RecordingTelemetry` installed for the duration of a `with` block."""

    def __enter__(self) -> RecordingTelemetry:
        self.fake = RecordingTelemetry()
        self.previous = otel.install(otel.TelemetryHost(active=self.fake))
        return self.fake

    def __exit__(self, *exc: Any) -> None:
        otel.install(self.previous)


class _Armed:
    """A scripted channel installed with a guaranteed disarm."""

    def __init__(self, *requests: control.Request) -> None:
        self.channel = control.FakeChannel(*requests)

    def __enter__(self) -> control.FakeChannel:
        control.arm(self.channel)
        return self.channel

    def __exit__(self, *exc: Any) -> None:
        control.arm(None)


@contextmanager
def _no_config_env() -> Iterator[None]:
    """A re-exec appends `--config` when one is set, and the machine running the tests may well have set one."""
    with patch.dict(run_mod.os.environ):
        run_mod.os.environ.pop(CONFIG_PATH_ENV, None)
        yield


def _raises(exc_type: type[BaseException], fn: Any, *args: Any, **kwargs: Any) -> BaseException:
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")




def test_a_reload_raised_from_a_state_body_closes_that_states_span():
    """The unclosed-span half of the feature, at its smallest."""

    class Cut(Workflow):
        def start(self) -> Transition:
            raise reload.ReloadRequested("cut mid-turn")

    with tempfile.TemporaryDirectory() as tmp, _Recording() as fake:
        env = _env(tmp)
        _raises(reload.ReloadRequested, drive, Cut(), env)

        assert [kind for kind, *_ in fake.states] == ["start", "end"], fake.states
        assert fake.states[-1][1:] == ("start", fake.states[0][2], None), fake.states
        assert fake.cuts == [("start", "reload")], fake.cuts


def test_a_reload_deep_in_a_sub_flow_closes_one_scope_per_drive_frame():
    """`drive` is re-entrant, which is the whole reason the request travels as an exception rather than swapping modules where it is noticed."""

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
        assert all(entry[3] is None for entry in fake.states if entry[0] == "end"), fake.states


def test_a_boundary_request_is_honoured_after_the_checkpoint_and_before_the_body():
    """The half the stream loop deliberately does not serve: a request that arrived while a script node ran, and the `--at-boundary` request it ignores by design."""
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
        assert channel.replies == [{"ok": True, "cut": False}], channel.replies


def test_a_profile_switch_is_applied_in_place_and_the_run_carries_on():
    """The opposite of a reload in the one way that matters: nothing unwinds."""
    ran: list[str] = []

    class Quiet(Workflow):
        def start(self) -> Transition:
            ran.append("start")
            return Done("finished")

    cfg = {"profiles": {"cheap": {"cli": "fake", "powers": {"high": {"model": "haiku"}}}}}
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
    """The installed channel is what scopes a request to a run."""

    class Quiet(Workflow):
        def start(self) -> Transition:
            return Done("finished")

    with tempfile.TemporaryDirectory() as tmp:
        control.arm(None)
        assert drive(Quiet(), _env(tmp)) == "finished"




class Stub(Workflow):
    """A one-state flow whose body never runs — `drive` is substituted in the tests below."""

    def start(self) -> Transition:
        return Done(None)


class _Registry(Registry):
    """A registry whose directory is this `tests/` folder — the same shim as test_run_terminal.py's."""

    def directory(self) -> Path:
        return Path(__file__).parent


def _build_registry() -> Registry:
    registry = _Registry("stub")
    registry.add_flows(main=Stub)
    registry.entry = Stub
    return registry


REGISTRY = _build_registry()


def _invocation(tmp: str, active: Any = None) -> RunInvocation:
    return RunInvocation(
        registry=REGISTRY,
        runs_dir=Path(tmp) / "runs",
        flow="main",
        run_id="t",
        telemetry=otel.TelemetryHost(
            settings=dataclasses.replace(otel.OtelSettings(), forced=True),
            build=lambda workflow, run_id, run_dir, settings: active
            or otel._NullTelemetry(),
        ),
    )


def test_a_run_listens_on_its_own_dir_and_stops_listening_on_the_way_out():
    """Opened after telemetry (so a cut turn's `reload_kill` event has a span to land on) and closed on every exit path, because the installed channel is process-wide and a socket left bound would make the *next* run in that dir look like a second listener."""
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
    """`--core` cannot be a module swap — `drive`, the ladder and `process.py` are all on the stack executing it — so the process image goes instead."""
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

    assert drives == 1
    assert [(name, attrs.get("core"), attrs.get("state")) for name, _, attrs in fake.events] == [
        ("reload", True, "start")
    ], fake.events
    assert control.armed().fileno() is None


def test_the_re_exec_argv_is_the_resume_spelling_not_the_original_one():
    """The original argv is not replayed: its `--param`/`--params-file` are already in the checkpoint the new image resumes from, so replaying them would let a file the operator edited meanwhile win over what the run actually holds."""
    calls: list[tuple[str, list[str]]] = []

    def fake_execv(path: str, argv: list[str]) -> None:
        calls.append((path, list(argv)))
        raise OSError("the console script moved")

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
    """The one thing a resume cannot read off the checkpoint."""
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
    """The two are the same claim about the same run — this process's re-exec line and the line a supervisor re-spawns off `launch.json` — and they were one copy-paste away from disagreeing."""
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
    """Two things the resume would otherwise get wrong."""
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
    """A request naming a CLI implies the process image, whatever its `core` flag says."""
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

    assert [(attrs.get("core"), attrs.get("cli")) for _, _, attrs in fake.events] == [
        (True, "claude")
    ], fake.events


def test_a_plain_core_reload_comes_back_on_the_cli_the_run_is_on():
    """A run an earlier `switch-cli` moved has no profile and a `run.json` still naming the one it launched with."""
    at_exec: list[tuple[str, str]] = []

    def fake_drive(wf: Any, env: Any, resume: Any = None) -> Any:
        env.writer.write_state_checkpoint("start", {}, inputs={}, flow="Stub", ctx={})
        raise reload.ReloadRequested("engine fix pushed", core=True)

    def fake_exec(name: str, run_dir: Path, *, cli: str = "", profile: str = "") -> int:
        at_exec.append((cli, profile))
        return reload.RELOAD_EXIT_CODE

    with tempfile.TemporaryDirectory() as tmp:
        invocation = dataclasses.replace(
            _invocation(tmp), config=RunConfig(backend=FakeBackend())
        )
        with (
            patch.object(run_mod, "drive", fake_drive),
            patch.object(run_mod, "_exec_reload", fake_exec),
        ):
            assert run_pyflow(invocation) == reload.RELOAD_EXIT_CODE
    assert at_exec == [("fake", "")], at_exec



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


_SPLIT_FLOW_V1 = '''
"""The broken flow, alone in its module — the composition root lives elsewhere."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from workhorse import reload
from workhorse.pyflow.workflow import Workflow

VERSION = "old"


class Probe(Workflow):
    def start(self) -> Any:
        here = Path(__file__)
        # The operator's push, standing in for a `git pull`.
        (here.parent / "pushed.py").replace(here)
        (self.run_dir / "ran-old.txt").write_text(VERSION, encoding="utf-8")
        raise reload.ReloadRequested("the operator cut this turn")
'''

_SPLIT_FLOW_V2 = '''
"""The pushed fix. Same state name, so the checkpoint still resolves."""

from __future__ import annotations

from typing import Any

from workhorse.pyflow.transitions import Done
from workhorse.pyflow.workflow import Workflow

VERSION = "new"


class Probe(Workflow):
    def start(self) -> Any:
        (self.run_dir / "ran-new.txt").write_text(VERSION, encoding="utf-8")
        return Done(VERSION)
'''

_SPLIT_WORKFLOW = '''
"""The composition root, in the place every real distribution keeps it."""

from __future__ import annotations

from split_probe.flow import Probe

from workhorse.pyflow.registry import Registry

workflow = Registry("probe")
workflow.add_flows(main=Probe)
workflow.entry = Probe
'''


def _write_split_package(root: Path) -> Any:
    """Materialise the split-layout distribution and import its composition root."""
    package = root / "split_probe"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "flow.py").write_text(_SPLIT_FLOW_V1, encoding="utf-8")
    (package / "pushed.py").write_text(_SPLIT_FLOW_V2, encoding="utf-8")
    (package / "workflow.py").write_text(_SPLIT_WORKFLOW, encoding="utf-8")
    sys.path.insert(0, str(root))
    importlib.invalidate_caches()
    return importlib.import_module("split_probe.workflow").workflow


def _forget_split(root: Path) -> None:
    for name in [m for m in sys.modules if m == "split_probe" or m.startswith("split_probe.")]:
        del sys.modules[name]
    if str(root) in sys.path:
        sys.path.remove(str(root))


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
    """The feature, end to end and with nothing about it faked."""
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
        assert (run_dir / "ran-new.txt").read_text(encoding="utf-8") == "new"
        assert control.armed().fileno() is None
        assert sorted(p.name for p in (Path(tmp) / "runs").iterdir()) == ["probe-probe"]


def test_a_reload_picks_up_a_fix_to_a_library_the_workflow_imports():
    """The failure this scope exists to prevent, stated as the operator meets it."""
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


def test_a_reload_finds_the_registry_in_its_own_composition_root():
    """The lookup goes to the module that composed the registry, not the entry class's."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "src"
        registry = _write_split_package(root)
        try:
            code = run_pyflow(
                dataclasses.replace(_invocation(tmp), registry=registry, run_id="split")
            )
        finally:
            _forget_split(root)

        run_dir = Path(tmp) / "runs" / "probe-split"
        assert code == 0, code
        assert (run_dir / "ran-old.txt").read_text(encoding="utf-8") == "old"
        assert (run_dir / "ran-new.txt").read_text(encoding="utf-8") == "new"


def test_the_environment_is_kept_while_the_working_tree_is_replaced():
    """The safety invariant, stated over the scan rather than over one reload."""
    site = Path(sysconfig.get_paths()["purelib"])
    tree = Path("/srv/checkout")
    fakes = {
        "vendored_dep": site / "vendored_dep" / "__init__.py",
        "vendored_dep.sub": site / "vendored_dep" / "sub.py",
        "probe_sibling": tree / "probe_sibling" / "__init__.py",
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

    assert roots[0] == "reloadable_probe"
    assert "probe_sibling" in roots
    assert "vendored_dep" not in roots
    assert "probe_namespace" not in roots
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
    test_a_reload_finds_the_registry_in_its_own_composition_root()
    test_the_environment_is_kept_while_the_working_tree_is_replaced()
    print("ok")
