"""Tests for the state graph read off a Python workflow's source, and `--dry-run`."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

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
from workhorse.manifest import ManifestContext  # noqa: E402
from workhorse.pyflow.dot import to_dot  # noqa: E402
from workhorse.pyflow.graph import (  # noqa: E402
    Edge,
    StateNode,
    Step,
    preflight,
    registry_graphs,
    state_graph,
)


class RegistryAt(Registry):
    """A registry whose workflow directory a test can point at a temp dir."""

    at: Path | None = None

    def directory(self) -> Path:
        return self.at if self.at is not None else super().directory()

Transition = Any


class Report(BaseModel):
    verdict: str = ""


bp = Blueprint("kit")


@bp.node
def measure(logger: Any, target: str) -> Report:
    """The verdict of measuring a target."""
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
        return Await("questions.md", found.verdict, self.finish, verdict=verdict)

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


class Factored(Workflow):
    """A machine whose seams live in private helpers, the way `research` factors them."""

    def start(self) -> Transition:
        self._record()
        return Continue(None, self.finish)

    def finish(self) -> Transition:
        self._ping()
        return Done(None)

    def _record(self) -> Report:
        self.call(measure, "acme")
        return self.agent("prompts/record.md", returns=Report)

    def _ping(self) -> None:
        self._pong()

    def _pong(self) -> None:
        self._ping()
        self.call(measure, "globex")


def _graph(cls: type[Workflow]):
    return state_graph(cls)


def _state(cls: type[Workflow], name: str) -> StateNode:
    """The named state, or a failure that says which one was missing."""
    node = _graph(cls).state(name)
    assert node is not None, name
    return node


def _edges(cls: type[Workflow], name: str) -> set[tuple[str, str]]:
    return {(edge.target, edge.kind) for edge in _state(cls, name).edges}




def test_both_arms_of_a_branch_become_edges():
    assert _edges(Sample, "start") == {("review", "continue"), ("retry", "continue")}


def test_a_done_is_an_edge_out_of_the_state_beside_its_other_edge():
    node = _state(Sample, "retry")
    assert _edges(Sample, "retry") == {("", "done"), ("start", "continue")}
    assert node.terminal
    assert not _state(Sample, "start").terminal


class Parent(Workflow):
    def start(self) -> Transition:
        return Done(self.handoff(Orphan))


class Reasoned(Workflow):
    """Every transition says why, one of them in a form the reader cannot print."""

    def start(self) -> Transition:
        if self.run_id:
            return Continue(None, self.hold, 1).because("a run id was given")
        why = "computed"
        return Continue(None, self.finish).because(f"no run id: {why}")

    def hold(self, attempt: int) -> Transition:
        return Await("q.md", "?", self.finish).because("someone must answer")

    def finish(self) -> Transition:
        return Done(None).because("nothing left to do")


def test_a_chained_because_is_read_as_the_edge_reason():
    start = {(e.target, e.kind, e.reason) for e in _state(Reasoned, "start").edges}
    assert start == {("hold", "continue", "a run id was given"), ("finish", "continue", "")}
    assert _state(Reasoned, "hold").edges == (
        Edge(target="finish", kind="await", reason="someone must answer"),
    )
    assert [(e.kind, e.reason) for e in _state(Reasoned, "finish").edges] == [
        ("done", "nothing left to do")
    ]


def test_dot_prefers_the_reason_over_parameter_names():
    dot = to_dot([_graph(Reasoned)])
    assert 'f0__start -> f0__hold [label="a run id was given"]' in dot
    assert 'label="attempt"' not in dot
    assert 'f0__finish -> f0____end [label="nothing left to do", color=darkgoldenrod]' in dot


def test_an_await_edge_is_read_from_the_third_argument():
    assert _edges(Sample, "review") == {("finish", "await")}


def test_edge_labels_name_the_parameters_the_transition_binds():
    start = _state(Sample, "start")
    by_target = {edge.target: edge.params for edge in start.edges}
    assert by_target["review"] == ("verdict",)
    assert by_target["retry"] == ("attempt",)


def test_node_calls_and_prompt_paths_are_collected():
    graph = _graph(Sample)
    assert _state(Sample, "start").calls == ("measure",)
    assert _state(Sample, "review").prompts == ("prompts/review.md",)
    assert graph.prompts() == (("review", "prompts/review.md"),)


def test_a_seam_inside_a_private_helper_is_attributed_to_the_state():
    graph = _graph(Factored)
    assert _state(Factored, "start").calls == ("measure",)
    assert _state(Factored, "start").prompts == ("prompts/record.md",)
    assert {node.name for node in graph.states} == {"start", "finish"}
    assert graph.prompts() == (("start", "prompts/record.md"),)


def test_helpers_that_call_each_other_do_not_loop_the_reader():
    assert _state(Factored, "finish").calls == ("measure",)


def test_an_alias_is_never_a_second_state():
    names = {node.name for node in _graph(Sample).states}
    assert "review" in names
    assert "qa" not in names


def test_a_target_the_source_cannot_name_is_reported_as_dynamic():
    edges = _state(Dynamic, "start").edges
    assert len(edges) == 1
    assert edges[0].dynamic
    assert _graph(Dynamic).unreachable() == ("finish",)


def test_reachability_finds_the_state_nothing_transitions_to():
    assert _graph(Orphan).unreachable() == ("stranded",)
    assert _graph(Sample).unreachable() == ()




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
            return Continue(None, self.output)  # ty: ignore[missing-argument]  # pyright: ignore[reportCallIssue, reportArgumentType]

        def finish(self) -> Transition:
            return Done(None)

    problems = preflight([_graph(Broken)])
    assert any("not a state" in p for p in problems), problems




_SAMPLE: Registry | None = None


def _sample_registry() -> Registry:
    """The one registry that owns `Sample`/`Orphan`, built once for the whole module."""
    global _SAMPLE
    if _SAMPLE is None:
        registry = Registry("acme").add_blueprints(bp)
        registry.entry_point(Sample)
        registry.add_flows(orphan=Orphan)
        _SAMPLE = registry
    return _SAMPLE


def test_registry_graphs_render_each_class_once_with_all_its_flow_names():
    graphs = registry_graphs(_sample_registry())
    assert [g.workflow for g in graphs] == ["Sample", "Orphan"]
    assert graphs[0].names == ("default",)
    assert graphs[1].label == "orphan"


def test_dot_renders_one_cluster_per_flow_with_live_names_only():
    dot = to_dot(registry_graphs(_sample_registry()), name="acme")
    assert dot.startswith("digraph acme {")
    assert dot.count("\n  subgraph cluster_") == 3
    assert "START" in dot
    assert '"qa' not in dot
    assert "review" in dot


def test_dot_draws_a_state_as_the_chain_of_steps_it_runs():
    """A state's box holds one bubble per seam, in source order, captioned with what the author wrote about it; transitions leave the last bubble and enter the first."""
    dot = to_dot([_graph(Factored)])
    assert "subgraph cluster_f0__start {" in dot
    assert 'f0__start__0 [label="measure' in dot
    assert 'f0__start__1 [label="record.md", shape=note' in dot
    assert "f0__start__0 -> f0__start__1" in dot
    assert "f0__start__1 -> f0__finish__0 [ltail=cluster_f0__start, lhead=cluster_f0__finish]" in dot
    assert "f0____start -> f0__start__0 [lhead=cluster_f0__start]" in dot
    plain = to_dot([_graph(Reasoned)])
    assert "cluster_f0__hold" not in plain
    assert 'f0__hold [label="hold"]' in plain


def test_a_step_carries_the_docstring_line_or_the_prompt_title(tmp_path: Path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("---\nagent: x\n---\n\n# Review the thing\n")
    graph = state_graph(Sample, workflow_dir=tmp_path)
    review = graph.state("review")
    assert review is not None
    assert [(s.kind, s.file, s.summary) for s in review.steps] == [
        ("agent", "review.md", "Review the thing")
    ]
    start = graph.state("start")
    assert start is not None and start.steps[0].summary == "The verdict of measuring a target."
    review = _state(Sample, "review")
    assert review.steps == (Step("agent", "prompts/review.md"),)


def test_dot_marks_an_await_edge_and_labels_bound_parameters():
    dot = to_dot([_graph(Sample)])
    assert "style=dashed" in dot
    assert 'label="verdict"' in dot


def test_dot_draws_done_as_an_edge_to_one_end_sink_per_flow():
    dot = to_dot([_graph(Sample)])
    assert "box3d" not in dot
    assert dot.count('label="END"') == 1
    assert "f0__retry -> f0____end" in dot
    assert "f0__finish -> f0____end" in dot
    assert "__end" not in to_dot([_graph(Endless)])


def test_dot_draws_a_handoff_as_a_coloured_bubble_and_never_an_edge():
    dot = to_dot([_graph(Parent), _graph(Orphan)])
    assert 'f0__start__0 [label="handoff → Orphan", shape=box, fillcolor=plum]' in dot
    assert "-> f1____start" not in dot
    assert "f1____end ->" not in dot
    assert "back to" not in dot
    assert "f1____start [" in dot and "f1____end [" in dot
    assert "fillcolor=lightgreen" in dot and "fillcolor=gold" in dot
    alone = to_dot([_graph(Parent)])
    assert 'label="handoff → Orphan"' in alone
    assert "f1____start" not in alone


def test_dot_ids_are_flow_prefixed_so_two_flows_may_share_a_state_name():
    dot = to_dot(registry_graphs(_sample_registry()))
    assert "f0__start" in dot
    assert "f1__start" in dot




def test_dry_run_reports_problems_and_never_opens_a_run_dir():
    from workhorse.pyflow import run as pyflow_run

    class Stranded(Workflow):
        def start(self) -> Transition:
            return Done(None)

        def stranded(self) -> Transition:
            return Done(None)

    registry = RegistryAt("acme")
    registry.at = Path("/nonexistent")
    registry.entry_point(Stranded)
    calls: list[str] = []
    original = pyflow_run.registry_graphs

    spy = patch.object(
        pyflow_run, "registry_graphs", lambda reg: (calls.append(reg.name), original(reg))[1]
    )
    with spy, tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        code = pyflow_run.run_pyflow(
            pyflow_run.RunInvocation(registry, runs_dir=runs, dry_run=True)
        )
        assert code == 1
        assert not runs.exists(), "a failed preflight must not open a run dir"
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

    registry = RegistryAt("acme")
    registry.add_blueprints(kit)
    registry.entry_point(Quick)
    with tempfile.TemporaryDirectory() as tmp:
        registry.at = Path(tmp)
        code = pyflow_run.run_pyflow(
            pyflow_run.RunInvocation(
                registry, runs_dir=Path(tmp) / "runs", run_id="real", dry_run=True
            )
        )
    assert code == 0
    assert ran == [], "a dry run must not execute a node"


def test_a_dry_run_records_which_stand_in_answered_each_seam():
    """`events.jsonl` is the durable record, so it has to say more than "entered"."""
    from workhorse.pyflow import run as pyflow_run

    kit = Blueprint("marks")

    @kit.node(stub=lambda logger: Report(verdict="stand-in"))
    def declared_node(logger: Any) -> Report:
        return Report(verdict="real")

    @kit.node
    def bare_node(logger: Any) -> Report:
        return Report(verdict="real")

    class Marked(Workflow):
        def start(self) -> Transition:
            self.call(declared_node)
            self.call(bare_node)
            self.agent("prompts/review.md", returns=Report)
            self.agent("prompts/record.md", returns=Report)
            return Done(None)

    registry = RegistryAt("acme")
    registry.add_blueprints(kit)
    registry.stub_agents({"review": {"verdict": "ok"}})
    registry.entry_point(Marked)
    with tempfile.TemporaryDirectory() as tmp:
        prompts = Path(tmp) / "prompts"
        prompts.mkdir()
        (prompts / "review.md").write_text("hi")
        (prompts / "record.md").write_text("hi")
        registry.at = Path(tmp)
        runs = Path(tmp) / "runs"
        code = pyflow_run.run_pyflow(
            pyflow_run.RunInvocation(registry, runs_dir=runs, dry_run=True)
        )
        lines = (runs / "acme-dry-run" / "events.jsonl").read_text().splitlines()

    assert code == 0
    events = [json.loads(line) for line in lines]
    entered = {
        e["node"]: e.get("stub")
        for e in events
        if e.get("phase") == "enter" and ("blueprint" in e or "prompt" in e)
    }
    assert entered == {
        "declared_node": "declared",
        "bare_node": "blank",
        "review": "declared",
        "record": "blank",
    }, entered


def test_dry_run_uses_its_own_run_dir_rather_than_a_real_runs_checkpoint():
    from workhorse.pyflow import run as pyflow_run

    class Quick(Workflow):
        def start(self) -> Transition:
            return Done(None)

    registry = RegistryAt("acme")
    registry.entry_point(Quick)
    with tempfile.TemporaryDirectory() as tmp:
        runs = Path(tmp) / "runs"
        registry.at = Path(tmp)
        pyflow_run.run_pyflow(
            pyflow_run.RunInvocation(
                registry, runs_dir=runs, run_id="week-long", dry_run=True
            )
        )
        assert not (runs / "acme-week-long").exists()
        assert (runs / "acme-dry-run").is_dir()


class Halts(Workflow):
    """A machine that can terminate either way, and whose measurement never says `ok`."""

    def start(self) -> Transition:
        report = self.call(measure, "over")
        if report.verdict == "ok":
            return Done(report)
        raise WorkflowFailed("budget exhausted")


_HALTING: RegistryAt | None = None


def _halting_registry() -> RegistryAt:
    """One registry for `Halts`, for the same reason `_sample_registry` is a singleton."""
    global _HALTING
    if _HALTING is None:
        registry = RegistryAt("acme")
        registry.add_blueprints(bp)
        registry.entry_point(Halts)
        _HALTING = registry
    return _HALTING


def _run_halting(*, dry_run: bool) -> tuple[int, str]:
    from workhorse.pyflow import run as pyflow_run

    registry = _halting_registry()
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        registry.at = Path(tmp)
        with contextlib.redirect_stdout(out):
            code = pyflow_run.run_pyflow(
                pyflow_run.RunInvocation(
                    registry, runs_dir=Path(tmp) / "runs", run_id="halt", dry_run=dry_run
                )
            )
    return code, out.getvalue()


def test_dry_run_reports_a_fail_terminal_rather_than_failing_on_it():
    code, out = _run_halting(dry_run=True)
    assert code == 0, out
    assert "fail terminal in 'start'" in out, out
    assert "budget exhausted" in out, out
    assert "stand-in values" in out, out


def test_a_real_run_still_fails_on_the_same_fail_terminal():
    code, out = _run_halting(dry_run=False)
    assert code == 1, out
    assert "ERROR: budget exhausted" in out, out


def _run_with_manifest(manifest: ManifestContext, *, dry_run: bool) -> tuple[int, str]:
    """Drive a trivial workflow whose one prompt names a skill, under `manifest`."""
    from workhorse.pyflow import run as pyflow_run

    class Named(Workflow):
        def start(self) -> Transition:
            return Done(None)

    registry = RegistryAt("acme")
    registry.entry_point(Named)
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as tmp:
        prompts = Path(tmp) / "prompts"
        prompts.mkdir()
        (prompts / "review.md").write_text(
            '{{ instruction_ref("story-docs") }}\n', encoding="utf-8"
        )
        registry.at = Path(tmp)
        with contextlib.redirect_stdout(out):
            code = pyflow_run.run_pyflow(
                pyflow_run.RunInvocation(
                    registry,
                    runs_dir=Path(tmp) / "runs",
                    run_id="refs",
                    dry_run=dry_run,
                    context_manifest=manifest,
                )
            )
    return code, out.getvalue()


def test_an_unresolvable_skill_reference_warns_a_real_run_and_fails_a_dry_one():
    """A `{{ instruction_ref(...) }}` that resolves against nothing renders a sentence of prose into a live agent prompt, so the only way it becomes visible is by being said."""
    manifest = ManifestContext(
        present=True, instructions={"go": ".claude/skills/acme-go/SKILL.md"}
    )

    code, out = _run_with_manifest(manifest, dry_run=False)
    assert code == 0, out
    assert "WARNING" in out and "story-docs" in out, out

    code, out = _run_with_manifest(manifest, dry_run=True)
    assert code == 1, out
    assert "ERROR" in out and "story-docs" in out, out


def test_a_run_carrying_no_manifest_is_not_warned_about_references():
    """Unresolved is the normal state for a manifest-free run (loop-runner, tests); warning there would train the operator to ignore the warning that matters."""
    code, out = _run_with_manifest(ManifestContext(), dry_run=True)
    assert code == 0, out
    assert "story-docs" not in out, out


def test_the_run_parser_carries_dry_run():
    from workhorse.cli.parser import build_parser

    args = build_parser(prog="workhorse-acme", workflow="acme").parse_args(
        ["run", "--dry-run"]
    )
    assert args.dry_run is True




def _dot_args(**kwargs: Any) -> Any:
    """The `dot` Namespace argparse would have built."""
    import argparse

    defaults = {"name": None, "output": None, "registry": None}
    return argparse.Namespace(**{**defaults, **kwargs})


def test_dot_renders_a_python_workflow_from_its_registry():
    import io
    from contextlib import redirect_stdout

    from workhorse.cli.dot import run as run_dot

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        run_dot(_dot_args(registry=_sample_registry()))
    assert buffer.getvalue().startswith("digraph acme {")


def test_dot_rejects_pin_and_leaf_at_the_parser():
    """`--pin`/`--leaf` collapsed a *declared* YAML branch."""
    from workhorse.cli.parser import build_parser

    for flag in ("--pin", "--leaf"):
        try:
            build_parser(prog="workhorse-acme", workflow="acme").parse_args(
                ["dot", flag, "mode=epic"]
            )
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"{flag} should no longer parse")


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
