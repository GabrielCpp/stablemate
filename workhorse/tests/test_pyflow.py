"""Tests for the Python state-machine engine (`workhorse.pyflow`).

Dependency-free and standalone, like the rest of `tests/`: nothing here touches the
network, the agent CLI or the clock. The agent seam is the run's own
`RunEnv.agent_runner` — a scripted stand-in for the recovery ladder, handed to the run
rather than assigned onto a module — and the `Await` wait is patched at
`workhorse.pyflow.driver._sleep`, so a test that exercises a week-long wait costs
microseconds.

What is asserted here is mostly the *contract* rather than the mechanics: the three
tiers of state, the `(state, params)` checkpoint, and the naming rules that decide
whether a run checkpointed on Tuesday can still resume on Friday after a rename.

Run: ./.venv/bin/python tests/test_pyflow.py   (or via pytest)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workhorse.artifacts import ArtifactWriter  # noqa: E402
from workhorse.config_run import RunConfig  # noqa: E402
from workhorse.pyflow import (  # noqa: E402
    Await,
    Blueprint,
    Continue,
    Done,
    NodeNotRunError,
    Registry,
    UnknownNodeError,
    UnknownStateError,
    Workflow,
    WorkflowDefinitionError,
    WorkflowFailed,
    WorkflowFrozenError,
    state,
)
from workhorse.pyflow import activity as pyflow_activity  # noqa: E402
from workhorse.pyflow import driver as pyflow_driver  # noqa: E402
from workhorse.pyflow import engine as pyflow_engine  # noqa: E402
from workhorse.pyflow.driver import Resume, drive, read_resume  # noqa: E402
from workhorse.pyflow.engine import RunEnv  # noqa: E402
from workhorse.pyflow.names import NameIndex  # noqa: E402

Transition = Any  # states are annotated loosely here; the driver checks the runtime type


# --------------------------------------------------------------------------- helpers


class ScriptedRunner:
    """A stand-in for the recovery ladder, whose `run` is whatever the test supplies.

    The ladder is the run's own dependency (`RunEnv.agent_runner`), so a test states
    what an agent turn replies by handing the run a different one — never by
    reassigning a function onto `pyflow.engine` (rule 5: a monkeypatched name is a
    missing injection point).
    """

    def __init__(self, run: Any) -> None:
        # An attribute, not a method: `env.agent_runner.run(...)` must call the
        # supplied function with the ladder's own arguments, unbound.
        self.run = run


def _env(tmp: str, *, name: str = "acme", **kwargs: Any) -> RunEnv:
    """A run environment rooted in `tmp`, with the agent backend stubbed out."""
    writer = ArtifactWriter(name, Path(tmp) / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        workflow_dir=Path(tmp),
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(backend_factory=lambda cli=None: None),
        **kwargs,
    )


def _checkpoint(env: RunEnv) -> dict[str, Any]:
    return json.loads((env.run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())


def _raises(exc_type: type[BaseException], fn: Any, *args: Any, **kwargs: Any) -> BaseException:
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    raise AssertionError(f"expected {exc_type.__name__}, nothing was raised")


# --------------------------------------------------------------------------- fixtures


class Payload(BaseModel):
    kind: str = "?"
    count: int = 0


bp = Blueprint("acme")


@bp.node
def measure(logger: Any, subject: str) -> Payload:
    logger.debug("measuring %s", subject)
    return Payload(kind=subject, count=len(subject))


@bp.node(aliases=["survey"])
def inventory(logger: Any) -> Payload:
    return Payload(kind="inventory", count=1)


# --------------------------------------------------------------- registration & names


def test_public_methods_are_states_and_helpers_are_not():
    class Discovered(Workflow):
        def start(self) -> Transition:
            return Done(None)

        def finish(self) -> Transition:
            return Done(None)

        def _helper(self) -> str:
            return "not a state"

        def setup(self) -> None:
            return None

        def labels(self) -> dict[str, str]:
            return {}

    assert set(Discovered.state_names()) == {"start", "finish"}, Discovered.state_names()


def test_aliases_resolve_but_do_not_show_up_as_live_names():
    class Renamed(Workflow):
        @state(aliases=["qa_gate"])
        def qa(self) -> Transition:
            return Done(None)

        def start(self) -> Transition:
            return Continue(None, self.qa)

    assert set(Renamed.state_names()) == {"start", "qa"}
    assert Renamed.resolve_state("qa_gate").name == "qa"
    assert Renamed.resolve_state("qa").name == "qa"


def test_an_alias_colliding_with_a_live_state_raises_at_registration():
    def define() -> type[Workflow]:
        class Collide(Workflow):
            @state(aliases=["start"])
            def qa(self) -> Transition:
                return Done(None)

            def start(self) -> Transition:
                return Done(None)

        return Collide

    exc = _raises(Exception, define)
    assert "start" in str(exc), exc


def test_two_nodes_claiming_one_name_raise_when_the_blueprints_merge():
    left, right = Blueprint("left"), Blueprint("right")

    @left.node
    def commit_all(logger: Any) -> None:
        return None

    @right.node(aliases=["commit_all"])
    def commit_everything(logger: Any) -> None:
        return None

    exc = _raises(Exception, Registry("acme").add_blueprints, left, right)
    assert "commit_all" in str(exc), exc


def test_node_names_are_live_names_only():
    assert "inventory" in bp.node_names()
    assert "survey" not in bp.node_names()


def test_a_dead_state_name_fails_loudly_and_names_the_fix():
    class Live(Workflow):
        def start(self) -> Transition:
            return Done(None)

    exc = _raises(UnknownStateError, Live.resolve_state, "gone")
    text = str(exc)
    assert "aliases=['gone']" in text, text
    assert "start" in text, text


# ----------------------------------------------------------------------- the run loop


class Linear(Workflow):
    subject: str

    def setup(self) -> Payload:
        return Payload(kind="ctx", count=7)

    def start(self) -> Transition:
        measured = self.call(measure, self.subject)
        return Continue(None, self.finish, count=measured.count)

    def finish(self, count: int) -> Transition:
        return Done({"count": count, "ctx": self.ctx.count})


def test_continue_and_done_drive_a_run_to_its_result():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        result = drive(Linear(subject="login"), env)
        assert result == {"count": 5, "ctx": 7}, result
        assert json.loads((env.run_dir / "run.json").read_text())["terminal"] == "terminal"


def test_the_checkpoint_is_the_state_and_its_params():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Stops(Workflow):
            subject: str

            def start(self) -> Transition:
                return Continue(None, self.boom, attempt=2)

            def boom(self, attempt: int) -> Transition:
                raise WorkflowFailed("deliberate")

        _raises(WorkflowFailed, drive, Stops(subject="login"), env)
        cp = _checkpoint(env)
        assert cp["engine"] == "pyflow", cp
        assert cp["state"] == "boom", cp
        assert cp["params"] == {"attempt": 2}, cp
        assert cp["flow"] == "Stops", cp
        assert cp["inputs"] == {"subject": "login"}, cp
        assert cp["waiting_on"] is None, cp


def test_a_transition_that_does_not_match_the_next_signature_fails_at_transition_time():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Mistyped(Workflow):
            def start(self) -> Transition:
                return Continue(None, self.finish, wrong=1)

            def finish(self, count: int) -> Transition:
                return Done(count)

        exc = _raises(TypeError, drive, Mistyped(), env)
        assert "does not match its signature" in str(exc), exc


def test_a_state_that_returns_something_else_is_a_loud_failure():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Sloppy(Workflow):
            def start(self) -> Transition:
                return "next please"

        exc = _raises(WorkflowFailed, drive, Sloppy(), env)
        assert "Continue" in str(exc), exc


def test_the_transition_budget_ends_a_ping_pong():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class PingPong(Workflow):
            max_transitions = 4

            def start(self) -> Transition:
                return Continue(None, self.pong)

            def pong(self) -> Transition:
                return Continue(None, self.start)

        exc = _raises(WorkflowFailed, drive, PingPong(), env)
        assert "transition budget exhausted after 4" in str(exc), exc


# --------------------------------------------------------------------------- freezing


def test_the_instance_freezes_once_setup_returns():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        wrote: list[str] = []

        class Freezes(Workflow):
            subject: str = "login"

            def setup(self) -> None:
                # setup() itself may still write — the freeze starts when it returns.
                self.subject = "settled"
                wrote.append(self.subject)
                return None

            def start(self) -> Transition:
                self.subject = "too late"
                return Done(None)

        exc = _raises(WorkflowFrozenError, drive, Freezes(), env)
        assert wrote == ["settled"], wrote
        assert "Continue(result, self.next_state, subject=" in str(exc), exc


# ----------------------------------------------------------------------------- resume


def test_a_resume_re_enters_the_checkpointed_state_without_re_running_setup():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        setups: list[int] = []

        class Resumed(Workflow):
            subject: str

            def setup(self) -> Payload:
                setups.append(1)
                return Payload(kind="ctx", count=7)

            def start(self) -> Transition:
                raise AssertionError("a resume must not re-enter start")

            def finish(self, count: int) -> Transition:
                return Done({"count": count, "ctx_kind": self.ctx.kind, "ctx": self.ctx.count})

        resume = Resume(
            state="finish",
            params={"count": 5},
            inputs={"subject": "login"},
            ctx={"kind": "ctx", "count": 7},
            flow="Resumed",
        )
        result = drive(Resumed(subject="login"), env, resume)
        assert result == {"count": 5, "ctx_kind": "ctx", "ctx": 7}, result
        assert setups == [], "setup() must not run again on a resume"


def test_a_checkpoint_written_under_the_old_name_resumes_the_renamed_state():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Renamed(Workflow):
            @state(aliases=["qa_gate"])
            def qa(self, story: str) -> Transition:
                return Done(story)

            def start(self) -> Transition:
                return Continue(None, self.qa, story="login")

        resume = Resume(state="qa_gate", params={"story": "login"}, flow="Renamed")
        assert drive(Renamed(), env, resume) == "login"
        # The checkpoint it rewrites carries the LIVE name, so the next resume is clean.
        assert _checkpoint(env)["state"] == "qa", _checkpoint(env)


def test_a_checkpoint_naming_a_dead_state_fails_rather_than_starting_over():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        entered: list[str] = []

        class Live(Workflow):
            def start(self) -> Transition:
                entered.append("start")
                return Done(None)

        resume = Resume(state="qa_gate", params={}, flow="Live")
        _raises(UnknownStateError, drive, Live(), env, resume)
        assert entered == [], "a dead state must not silently restart the run"


def test_checkpoint_params_are_coerced_back_into_their_declared_types():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        seen: list[Any] = []

        class Typed(Workflow):
            def start(self) -> Transition:
                return Done(None)

            def finish(self, where: Path) -> Transition:
                seen.append(where)
                return Done(None)

        drive(Typed(), env, Resume(state="finish", params={"where": "docs/epics"}))
        assert seen == [Path("docs/epics")], seen


def test_a_checkpoint_param_the_state_does_not_have_is_reported_by_name():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Typed(Workflow):
            def start(self, count: int = 0) -> Transition:
                return Done(None)

        exc = _raises(
            WorkflowFailed, drive, Typed(), env, Resume(state="start", params={"nope": 1})
        )
        assert "nope" in str(exc), exc


def test_read_resume_refuses_a_yaml_checkpoint():
    exc = _raises(WorkflowFailed, read_resume, {"current_id": "plan", "context": {}})
    assert "YAML engine" in str(exc), exc
    assert "plan" in str(exc), exc


# ------------------------------------------------------------------------ self.output


def test_output_reads_the_recorded_value_back_typed():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Reads(Workflow):
            def start(self) -> Transition:
                self.call(measure, "login")
                return Continue(None, self.finish)

            def finish(self) -> Transition:
                later = self.output(measure)
                return Done((type(later).__name__, later.kind, later.count))

        assert drive(Reads(), env) == ("Payload", "login", 5)


def test_output_resolves_the_latest_invocation():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Twice(Workflow):
            def start(self) -> Transition:
                self.call(measure, "a")
                self.call(measure, "abcd")
                return Done(self.output(measure).count)

        assert drive(Twice(), env) == 4


def test_output_raises_when_the_node_has_not_run():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class Forgot(Workflow):
            def start(self) -> Transition:
                return Done(self.output(measure))

        exc = _raises(NodeNotRunError, drive, Forgot(), env)
        assert "has no recorded output" in str(exc), exc


def test_output_falls_back_to_a_directory_written_under_the_old_node_name():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        # What a run started before the rename left on disk.
        env.writer.write_step("survey", "survey()\n", {"kind": "old", "count": 3}, {})

        class Reads(Workflow):
            def start(self) -> Transition:
                return Done(self.output(inventory).count)

        assert drive(Reads(), env) == 3


# ----------------------------------------------------------------------------- Await


def test_await_writes_the_ask_and_checkpoints_before_it_waits():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)
        ask = Path(tmp) / "docs" / "questions.md"
        observed: list[dict[str, Any]] = []

        class Blocks(Workflow):
            def start(self) -> Transition:
                return Await(ask, "which branch?", self.resumed, answer="pending")

            def resumed(self, answer: str) -> Transition:
                return Done(ask.read_text().strip())

        def fake_sleep(_seconds: float) -> None:
            observed.append({**_checkpoint(env), "ask": ask.read_text()})
            ask.write_text("main\n")
            stamp = ask.stat().st_mtime + 3600
            os.utime(ask, (stamp, stamp))

        real_sleep = pyflow_driver._sleep
        pyflow_driver._sleep = fake_sleep
        try:
            assert drive(Blocks(), env) == "main"
        finally:
            pyflow_driver._sleep = real_sleep

        assert len(observed) == 1, observed
        assert observed[0]["ask"] == "which branch?", observed[0]
        assert observed[0]["state"] == "resumed", observed[0]
        assert observed[0]["params"] == {"answer": "pending"}, observed[0]
        assert observed[0]["waiting_on"] == str(ask), observed[0]


# ---------------------------------------------------------------------- self.handoff


def test_handoff_drives_a_sub_flow_in_its_own_scope_and_returns_its_result():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp)

        class SubFlow(Workflow):
            token: str

            def start(self) -> Transition:
                self.call(measure, self.token)
                return Done({"token": self.token})

        class Parent(Workflow):
            def start(self) -> Transition:
                return Done(self.handoff(SubFlow, token="login"))

        assert drive(Parent(), env) == {"token": "login"}
        # The sub-flow's nodes live under the handoff's own scope, so a node name
        # reused by parent and child cannot overwrite the other's output.json.
        assert (env.run_dir / "sub_flow" / "_flow" / "measure" / "output.json").is_file()
        assert not (env.run_dir / "measure").exists()


# ------------------------------------------------------------------------ self.agent


def test_agent_validates_the_reply_into_the_declared_model():
    with tempfile.TemporaryDirectory() as tmp:
        calls: list[Any] = []

        def fake_run_agent(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
            calls.append((node.id, [o.key for o in node.outputs], ctx.as_dict()))
            return "rendered prompt", {"kind": "reviewed", "count": 2}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run_agent))

        class Asks(Workflow):
            def start(self) -> Transition:
                reply = self.agent(
                    "prompts/review.md", returns=Payload, args={"subject": "login"}
                )
                return Done((reply.kind, reply.count))

        assert drive(Asks(), env) == ("reviewed", 2)

        assert calls[0][0] == "review", calls
        assert calls[0][1] == ["kind", "count"], calls
        assert calls[0][2] == {"subject": "login"}, calls
        assert (env.run_dir / "review" / "prompt.md").read_text() == "rendered prompt"


def test_agent_carries_cwd_and_add_dirs_onto_the_node():
    """`cwd` decides whose CLAUDE.md, skills and git context a turn sees, so a
    workflow that runs against a checkout it computed must be able to say where.
    They land on the same `AgentNode` the YAML engine builds, so the render, the
    de-dupe and the `--add-dir` flags are the runner's existing behavior."""
    with tempfile.TemporaryDirectory() as tmp:
        nodes: list[Any] = []

        def fake_run_agent(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
            nodes.append(node)
            return "rendered", {"kind": "ok", "count": 0}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run_agent))

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent(
                    "prompts/review.md",
                    returns=Payload,
                    cwd=Path("/repos/acme"),
                    add_dirs=["/repos/docs", Path("/repos/api-service")],
                )
                # Saying nothing must leave the model's own defaults in place
                # rather than overwrite them with None.
                self.agent("prompts/plain.md", returns=Payload)
                return Done(None)

        drive(Asks(), env)

        assert nodes[0].cwd == "/repos/acme", nodes[0]
        assert nodes[0].add_dirs == ["/repos/docs", "/repos/api-service"], nodes[0]
        assert nodes[1].cwd is None, nodes[1]
        assert nodes[1].add_dirs == [], nodes[1]


def test_the_context_manifest_is_the_outer_layer_of_an_agent_turn():
    """A ported library prompt calls `instruction_ref(...)` / `template.*`, and those
    helpers read the farrier manifest off the render context. It is the OUTER layer —
    always present so they resolve, always overridable by the state's own arguments,
    which is the same precedence the YAML engine gives it."""
    with tempfile.TemporaryDirectory() as tmp:
        seen: list[Any] = []

        def fake_run_agent(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
            seen.append(ctx.as_dict())
            return "rendered", {"kind": "ok", "count": 0}

        env = _env(
            tmp,
            agent_runner=ScriptedRunner(fake_run_agent),
            manifest={
                "_instructions": {"go": ".claude/skills/acme-go/SKILL.md"},
                "template": {"backend_layer_name": "Go gateway"},
                "unit": "from-the-manifest",
            },
        )

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent(
                    "prompts/review.md", returns=Payload, args={"unit": "CASE-1"}
                )
                return Done(None)

        drive(Asks(), env)

        ctx = seen[0]
        assert ctx["_instructions"] == {"go": ".claude/skills/acme-go/SKILL.md"}
        assert ctx["template"] == {"backend_layer_name": "Go gateway"}
        assert ctx["unit"] == "CASE-1", "the state's own argument wins"


def test_a_run_with_no_manifest_renders_exactly_its_arguments():
    """The manifest-free case (hello-world, most tests) must add no keys at all —
    an empty seat, not a placeholder one."""
    with tempfile.TemporaryDirectory() as tmp:
        seen: list[Any] = []

        def fake_run_agent(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
            seen.append(ctx.as_dict())
            return "rendered", {"kind": "ok", "count": 0}

        env = _env(tmp, agent_runner=ScriptedRunner(fake_run_agent))

        class Asks(Workflow):
            def start(self) -> Transition:
                self.agent("prompts/p.md", returns=Payload, args={"unit": "CASE-1"})
                return Done(None)

        drive(Asks(), env)

        assert seen[0] == {"unit": "CASE-1"}


# ---------------------------------------------------------------------------- activity


def test_a_states_flagged_log_line_becomes_the_run_activity():
    """The YAML engine's per-node `activity:` has no counterpart in a state machine —
    a state is one method that may do several things. So the run's activity is
    whichever log line most recently flagged itself, and the driver's per-transition
    label rebase preserves it. See `tests/test_activity.py` for the semantics."""
    with tempfile.TemporaryDirectory() as tmp:
        # Its own logger, at INFO: a logger left at the root's inherited WARNING drops
        # the flagged record before any filter sees it, and the test would pass blind.
        log = logging.getLogger("tests.pyflow.activity")
        log.setLevel(logging.INFO)
        log.filters.clear()

        env = _env(tmp, log=log)
        published: list[dict[str, str]] = []
        real = pyflow_activity.otel.set_labels
        pyflow_activity.otel.set_labels = published.append
        try:

            class Narrates(Workflow):
                def labels(self) -> dict[str, str]:
                    return {"work_id": "ACME-9"}

                def start(self) -> Transition:
                    self.logger.info(
                        "assessing %s", "legacy/report/list", extra={"activity": True}
                    )
                    return Continue(None, self.finish)

                def finish(self) -> Transition:
                    return Done("ok")

            assert drive(Narrates(), env) == "ok"
        finally:
            pyflow_activity.otel.set_labels = real

        # The flagged line publishes, and the transition into `finish` rebases the
        # declared labels without clearing it.
        assert published[-1] == {
            "work_id": "ACME-9",
            "activity": "assessing legacy/report/list",
        }, published


# --------------------------------------------------------------------------- dry run


def test_dry_run_records_the_calls_without_making_them():
    with tempfile.TemporaryDirectory() as tmp:
        env = _env(tmp, dry_run=True)
        ran: list[str] = []

        blueprint = Blueprint("acme")

        @blueprint.node
        def touch_the_world(logger: Any) -> Payload:
            ran.append("touch_the_world")
            return Payload(kind="real", count=1)

        class Walks(Workflow):
            def start(self) -> Transition:
                self.call(touch_the_world)
                return Continue(None, self.finish)

            def finish(self) -> Transition:
                return Done(None)

        drive(Walks(), env)
        assert ran == [], "a dry run must not execute node bodies"
        assert (env.run_dir / "touch_the_world" / "output.json").is_file()


# ------------------------------------------------------------- the composition root


def test_the_run_index_supplies_the_body_the_callsite_only_names():
    """`self.call(measure, …)` passes the function because `Concatenate[Logger, P]`
    needs it for typing; what runs is whatever the run's index holds under that name.
    That is the whole seam — a test substitutes instead of patching the node's module."""
    with tempfile.TemporaryDirectory() as tmp:
        registry = Registry("acme").add_blueprints(bp)

        class Calls(Workflow):
            def start(self) -> Transition:
                return Done(self.call(measure, "login").kind)

        env = _env(tmp, nodes=registry.override(measure=lambda logger, subject: Payload(
            kind=f"substituted:{subject}", count=0
        )))
        assert drive(Calls(), env) == "substituted:login"
        # Non-mutating: the registry every other run in the process shares is untouched.
        assert registry.nodes.get("measure").fn is measure


def test_overriding_a_node_the_registry_does_not_have_names_the_registered_ones():
    registry = Registry("acme").add_blueprints(bp)
    exc = _raises(WorkflowDefinitionError, registry.override, mesure=lambda logger: None)
    assert "no node 'mesure'" in str(exc), exc
    assert "measure" in str(exc), exc


def test_a_node_missing_from_the_run_index_is_an_error_not_a_fallback():
    """Falling back to the stamp would make the seam advisory — holding or not
    depending on whether the node's blueprint had been folded in, which is the bug
    `add_blueprints` exists to remove."""
    with tempfile.TemporaryDirectory() as tmp:
        other = Blueprint("globex")

        @other.node
        def unrelated(logger: Any) -> Payload:
            return Payload()

        class Calls(Workflow):
            def start(self) -> Transition:
                return Done(self.call(measure, "login"))

        env = _env(tmp, nodes=Registry("globex").add_blueprints(other).nodes)
        exc = _raises(UnknownNodeError, drive, Calls(), env)
        assert "add_blueprints" in str(exc), exc
        assert "unrelated" in str(exc), exc


def test_a_declared_stub_is_what_a_dry_run_runs_in_place_of_the_node():
    with tempfile.TemporaryDirectory() as tmp:
        blueprint = Blueprint("acme")

        @blueprint.node(stub=lambda logger: Payload(kind="stand-in", count=7))
        def touch_the_world(logger: Any) -> Payload:
            raise AssertionError("a dry run must not execute node bodies")

        registry = Registry("acme").add_blueprints(blueprint)

        class Walks(Workflow):
            def start(self) -> Transition:
                reading = self.call(touch_the_world)
                return Done((reading.kind, reading.count))

        env = _env(tmp, dry_run=True, nodes=pyflow_engine.stub_nodes(registry.nodes))
        assert drive(Walks(), env) == ("stand-in", 7)


def test_a_dry_run_answers_a_prompt_with_the_reply_the_registry_declared():
    """Undeclared, every reply is a blank model and the machine takes whichever branch
    a blank selects. Declaring one per stem is what turns a dry run into a smoke test
    of the workflow's own happy path."""
    with tempfile.TemporaryDirectory() as tmp:
        registry = Registry("acme").stub_agents(
            {"review": {"kind": "approved", "count": 3}}
        )

        class Asks(Workflow):
            def start(self) -> Transition:
                reply = self.agent("prompts/review.md", returns=Payload, args={"n": 1})
                blank = self.agent("prompts/unlisted.md", returns=Payload)
                return Done((reply.kind, reply.count, blank.kind))

        env = _env(tmp, dry_run=True, agent_stubs=registry.agent_stubs)
        assert drive(Asks(), env) == ("approved", 3, "?")


def test_the_agent_ladder_is_a_run_dependency_not_a_module_attribute():
    with tempfile.TemporaryDirectory() as tmp:
        seen: list[str] = []

        def scripted(node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
            seen.append(node.id)
            return "rendered", {"kind": "injected", "count": 0}

        class Asks(Workflow):
            def start(self) -> Transition:
                return Done(self.agent("prompts/review.md", returns=Payload).kind)

        env = _env(tmp, agent_runner=ScriptedRunner(scripted))
        assert drive(Asks(), env) == "injected"
        assert seen == ["review"], seen


def test_a_handoff_into_another_registrys_flow_runs_in_that_registrys_world():
    """A sub-flow is a different program: it renders its own `prompts/` and calls its
    own nodes, so one shipped in another distribution does not look for its templates
    under its caller's package — and a node its caller substituted stays real for it."""
    with tempfile.TemporaryDirectory() as tmp:
        child_bp = Blueprint("globex")

        @child_bp.node
        def measure(logger: Any, subject: str) -> Payload:
            return Payload(kind=f"child:{subject}", count=0)

        class SubFlow(Workflow):
            def start(self) -> Transition:
                return Done(self.call(measure, "login").kind)

        # A registry's directory comes from the package its entry class lives in;
        # a class declared in a test file has none, so borrow a real package's.
        SubFlow.__module__ = "workhorse.pyflow.registry"
        child = Registry("globex").add_blueprints(child_bp)
        child.main(SubFlow)

        class Parent(Workflow):
            def start(self) -> Transition:
                return Done(self.handoff(SubFlow))

        parent = Registry("acme").add_blueprints(bp)
        env = _env(tmp, nodes=parent.override(measure=lambda logger, subject: Payload(
            kind="parent-substituted", count=0
        )))
        assert drive(Parent(), env) == "child:login"


def test_a_flow_class_may_belong_to_only_one_registry():
    class Shared(Workflow):
        def start(self) -> Transition:
            return Done(None)

    Registry("acme").add_flows(shared=Shared)
    exc = _raises(WorkflowDefinitionError, Registry("globex").add_flows, shared=Shared)
    assert "two workflows" in str(exc), exc


# -------------------------------------------------------------------------- Registry


def test_main_returns_the_console_callable_rather_than_running_anything():
    registry = Registry("acme")
    entry = registry.main(Linear)
    assert callable(entry)
    assert entry.__name__ == "main"
    assert registry.flow(None) is Linear
    assert registry.flow_names() == ["default"]
    assert registry.class_named("Linear") is Linear
    assert registry.class_named("Nope") is None


def test_a_registry_without_a_name_cannot_be_a_command():
    exc = _raises(WorkflowDefinitionError, Registry().main, Linear)
    assert "Registry(" in str(exc), exc


def test_a_name_index_rejects_a_second_claim_on_one_name():
    index: NameIndex[str] = NameIndex("state", owner="Test")
    index.register("qa", "first")
    _raises(Exception, index.register, "qa", "second")


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
