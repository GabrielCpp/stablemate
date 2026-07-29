"""Tests for the state graph read off a Python workflow's source, and `--dry-run`.

Dependency-free and standalone like the rest of `tests/`. Nothing here runs an agent:
the point of both features under test is precisely that nothing has to.

The graph is an over-approximation by design, so what is asserted is that it
over-approximates in the right direction — both arms of a branch appear, an alias never
does, and a target the code cannot name statically is reported as unknown rather than
guessed at.

Run: uv run python tests/test_pyflow_graph.py   (or via pytest)
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse.pyflow import (  # noqa: E402
    Await,
    Blueprint,
    Continue,
    Done,
    Registry,
    Workflow,
    WorkflowFailed,
    state,
)
from workhorse.pyflow.dot import to_dot  # noqa: E402
from workhorse.pyflow.graph import preflight, registry_graphs, state_graph  # noqa: E402

Transition = Any


class Report(BaseModel):
    verdict: str = ""


bp = Blueprint("kit")


@bp.node
def measure(logger: Any, target: str) -> Report:
    return Report(verdict=target)


class Sample(Workflow):
    """A machine with one branch, one loop, an await and a node call."""

    target: str = "acme"

    def start(self) -> Transition:
        report = self.call(measure, self.target)
        if report.verdict == "ok":
            return Continue(None, self.review, verdict=report.verdict)
        return Continue(None, self.retry, 1)

    def retry(self, attempt: int) -> Transition:
        if attempt > 3:
            return Done("gave up")
        return Continue(None, self.start)

    @state(aliases=["qa"])
    def review(self, verdict: str) -> Transition:
        found = self.agent("prompts/review.md", returns=Report)
        return Await("questions.md", [found.verdict], self.finish, verdict=verdict)

    def finish(self, verdict: str) -> Transition:
        return Done(verdict)


class Orphan(Workflow):
    def start(self) -> Transition:
        return Done(None)

    def stranded(self) -> Transition:
        return Done(None)


class Dynamic(Workflow):
    def start(self) -> Transition:
        target = self.finish if self.run_id else self.start
        return Continue(None, target)

    def finish(self) -> Transition:
        return Done(None)


class Endless(Workflow):
    def start(self) -> Transition:
        return Continue(None, self.start)


def _graph(cls: type[Workflow]):
    return state_graph(cls)


def _edges(cls: type[Workflow], name: str) -> set[tuple[str, str]]:
    node = _graph(cls).state(name)
    assert node is not None, name
    return {(edge.target, edge.kind) for edge in node.edges}


# --------------------------------------------------------------------------- reading


def test_both_arms_of_a_branch_become_edges():
    assert _edges(Sample, "start") == {("review", "continue"), ("retry", "continue")}


def test_a_state_that_can_end_is_terminal_and_still_has_its_other_edge():
    node = _graph(Sample).state("retry")
    assert node.terminal
    assert {edge.target for edge in node.edges} == {"start"}


def test_an_await_edge_is_read_from_the_third_argument():
    assert _edges(Sample, "review") == {("finish", "await")}


def test_edge_labels_name_the_parameters_the_transition_binds():
    start = _graph(Sample).state("start")
    by_target = {edge.target: edge.params for edge in start.edges}
    assert by_target["review"] == ("verdict",)
    # Positional: read off the target's own signature, the way the driver binds it.
    assert by_target["retry"] == ("attempt",)


def test_node_calls_and_prompt_paths_are_collected():
    graph = _graph(Sample)
    assert graph.state("start").calls == ("measure",)
    assert graph.state("review").prompts == ("prompts/review.md",)
    assert graph.prompts() == (("review", "prompts/review.md"),)


def test_an_alias_is_never_a_second_state():
    names = {node.name for node in _graph(Sample).states}
    assert "review" in names
    assert "qa" not in names


def test_a_target_the_source_cannot_name_is_reported_as_dynamic():
    edges = _graph(Dynamic).state("start").edges
    assert len(edges) == 1
    assert edges[0].dynamic
    # …and it stops reachability rather than pretending to reach everything.
    assert _graph(Dynamic).unreachable() == ("finish",)


def test_reachability_finds_the_state_nothing_transitions_to():
    assert _graph(Orphan).unreachable() == ("stranded",)
    assert _graph(Sample).unreachable() == ()


# ------------------------------------------------------------------------- preflight


def test_preflight_is_quiet_when_every_prompt_resolves():
    with tempfile.TemporaryDirectory() as tmp:
        prompts = Path(tmp) / "prompts"
        prompts.mkdir()
        (prompts / "review.md").write_text("hi")
        assert preflight([_graph(Sample)], Path(tmp)) == []


def test_preflight_names_the_prompt_that_does_not_exist():
    with tempfile.TemporaryDirectory() as tmp:
        problems = preflight([_graph(Sample)], Path(tmp))
    assert len(problems) == 1, problems
    assert "prompts/review.md" in problems[0]
    assert "review" in problems[0]


def test_preflight_reports_an_unreachable_state():
    problems = preflight([_graph(Orphan)])
    assert any("stranded" in p and "unreachable" in p for p in problems), problems


def test_preflight_reports_a_machine_that_cannot_terminate():
    problems = preflight([_graph(Endless)])
    assert any("Done" in p for p in problems), problems


def test_preflight_reports_a_transition_to_something_that_is_not_a_state():
    class Broken(Workflow):
        def start(self) -> Transition:
            return Continue(None, self.output)

        def finish(self) -> Transition:
            return Done(None)

    problems = preflight([_graph(Broken)])
    assert any("not a state" in p for p in problems), problems


# ------------------------------------------------------------------------------ dot


def _sample_registry() -> Registry:
    registry = Registry("acme").add_blueprints(bp)
    registry.main(Sample)
    registry.add_flows(orphan=Orphan)
    return registry


def test_registry_graphs_render_each_class_once_with_all_its_flow_names():
    graphs = registry_graphs(_sample_registry())
    assert [g.workflow for g in graphs] == ["Sample", "Orphan"]
    assert graphs[0].names == ("default",)
    assert graphs[1].label == "orphan"


def test_dot_renders_one_cluster_per_flow_with_live_names_only():
    dot = to_dot(registry_graphs(_sample_registry()), name="acme")
    assert dot.startswith("digraph acme {")
    assert dot.count("subgraph cluster_") == 2
    assert "START" in dot
    assert '"qa' not in dot  # the alias is not a node
    assert "review" in dot


def test_dot_marks_an_await_edge_and_labels_bound_parameters():
    dot = to_dot([_graph(Sample)])
    assert "style=dashed" in dot
    assert 'label="verdict"' in dot


def test_dot_ids_are_flow_prefixed_so_two_flows_may_share_a_state_name():
    dot = to_dot(registry_graphs(_sample_registry()))
    assert "f0__start" in dot
    assert "f1__start" in dot


# -------------------------------------------------------------------------- dry-run


def test_dry_run_reports_problems_and_never_opens_a_run_dir():
    from workhorse.pyflow import run as pyflow_run

    registry = Registry("acme")
    registry.main(Orphan)
    calls: list[str] = []
    original = pyflow_run.registry_graphs

    def fake_directory() -> Path:
        return Path("/nonexistent")

    registry.directory = fake_directory  # type: ignore[method-assign]
    pyflow_run.registry_graphs = lambda reg: (calls.append(reg.name), original(reg))[1]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / "runs"
            code = pyflow_run.run_pyflow(registry, runs_dir=runs, dry_run=True)
            assert code == 1
            assert not runs.exists(), "a failed preflight must not open a run dir"
    finally:
        pyflow_run.registry_graphs = original
    assert calls == ["acme"]


def test_dry_run_drives_the_machine_without_running_a_node():
    from workhorse.pyflow import run as pyflow_run

    ran: list[str] = []

    kit = Blueprint("dry")

    @kit.node
    def touch(logger: Any) -> Report:
        ran.append("touch")
        return Report(verdict="real")

    class Quick(Workflow):
        def start(self) -> Transition:
            self.call(touch)
            return Done("finished")

    registry = Registry("acme").add_blueprints(kit)
    registry.main(Quick)
    with tempfile.TemporaryDirectory() as tmp:
        registry.directory = lambda: Path(tmp)  # type: ignore[method-assign]
        code = pyflow_run.run_pyflow(
            registry, runs_dir=Path(tmp) / "runs", run_id="real", dry_run=True
        )
    assert code == 0
    assert ran == [], "a dry run must not execute a node"


def test_dry_run_uses_its_own_run_dir_rather_than_a_real_runs_checkpoint():
    from workhorse.pyflow import run as pyflow_run

    class Quick(Workflow):
        def start(self) -> Transition:
            return Done(None)

    registry = Registry("acme")
    registry.main(Quick)
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        registry.directory = lambda: Path(tmp)  # type: ignore[method-assign]
        pyflow_run.run_pyflow(registry, runs_dir=runs, run_id="week-long", dry_run=True)
        assert not (runs / "acme-week-long").exists()
        assert (runs / "acme-dry-run").is_dir()


class Halts(Workflow):
    """A machine that can terminate either way, and whose measurement never says `ok`.

    Both terminals are statically present, so the preflight passes; what decides which
    one runs is a value — which is exactly the position a stand-in reply puts every
    branch in under `--dry-run`.
    """

    def start(self) -> Transition:
        report = self.call(measure, "over")
        if report.verdict == "ok":
            return Done(report)
        raise WorkflowFailed("budget exhausted")


def _run_halting(*, dry_run: bool) -> tuple[int, str]:
    from workhorse.pyflow import run as pyflow_run

    registry = Registry("acme").add_blueprints(bp)
    registry.main(Halts)
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        registry.directory = lambda: Path(tmp)  # type: ignore[method-assign]
        with contextlib.redirect_stdout(out):
            code = pyflow_run.run_pyflow(
                registry, runs_dir=Path(tmp) / "runs", run_id="halt", dry_run=dry_run
            )
    return code, out.getvalue()


def test_dry_run_reports_a_fail_terminal_rather_than_failing_on_it():
    # Under `--dry-run` every agent reply is a blank stand-in, so the machine takes
    # whichever branch a blank selects — which for any workflow with a reachable fail
    # terminal can be that terminal. The check is what passed; say where it landed.
    code, out = _run_halting(dry_run=True)
    assert code == 0, out
    assert "fail terminal in 'start'" in out, out
    assert "budget exhausted" in out, out
    assert "stand-in values" in out, out


def test_a_real_run_still_fails_on_the_same_fail_terminal():
    code, out = _run_halting(dry_run=False)
    assert code == 1, out
    assert "ERROR: budget exhausted" in out, out


def test_the_run_parser_carries_dry_run():
    from workhorse.main import _build_parser

    args = _build_parser().parse_args(["run", "acme", "--dry-run"])
    assert args.dry_run is True


# ------------------------------------------------------------------------ dot (CLI)


def _dot_args(**kwargs: Any) -> Any:
    """The `dot` Namespace argparse would have built, with `registry` pre-resolved.

    `registry` is the seam the CLI itself uses: `_run_dot` prefers one already on the
    args over resolving the name through the installed entry points, so a test never
    has to install a distribution to render one.
    """
    import argparse

    defaults = {
        "workflow": None,
        "positional": [],
        "pin": None,
        "leaf": None,
        "name": None,
        "output": None,
        "registry": None,
    }
    return argparse.Namespace(**{**defaults, **kwargs})


def test_dot_renders_a_python_workflow_from_its_registry():
    import io
    from contextlib import redirect_stdout

    from workhorse.main import _run_dot

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        _run_dot(_dot_args(positional=["acme"], registry=_sample_registry()))
    assert buffer.getvalue().startswith("digraph acme {")


def test_dot_declines_pin_and_leaf_on_a_python_workflow():
    from workhorse.main import _run_dot

    try:
        _run_dot(_dot_args(positional=["acme"], registry=_sample_registry(), pin=["mode=epic"]))
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("--pin should be declined, not ignored")


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
