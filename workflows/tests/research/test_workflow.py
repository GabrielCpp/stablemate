"""End-to-end drives of the `research` state machine (`research/workflow.py`).

Three things are substituted and nothing else is: the agent turn, the clone, and the
four measurement nodes that would otherwise launch a real detached process for hours.
`load_program`, `record_spend`, `check_envelope` and `publish_results` run for real
against a temporary git repo built by :func:`_program_repo`, so a run here exercises
manifest parsing, the envelope arithmetic, the `Program` `setup()` residue every state
reads, and a real commit onto the result branch.

Every substitution is **supplied**, not patched: a run's node index and its agent
backend are fields of `RunEnv`, so `_env` hands over a scripted agent and a scripted
set of measurement nodes, and nothing here assigns over a module attribute it then has
to remember to restore. The one exception is `wait_for_answer`, which is a module
function the driver calls rather than a field — and it is patched because a test must
never actually block on a file a human is supposed to edit.

What is under test is the loop's arithmetic and, above all, **who each failure goes
to**. The graph's whole point is that "measured and missed", "produced no measurement"
and "the apparatus is broken" are three different things with three different owners:
a rework goes to the scientist, a crash in repo code goes to the engineer with no
person in the loop, and a tooling fault parks on an operator immediately. Those are
asserted as *paths*, from outside, by which prompt ran next.

The other invariant is negative and just as load-bearing: **no arm ends in
`WorkflowFailed`**. Every exhausted budget parks (`Await`) or escalates to the lead.
`_Parked` is how a park is observed without hanging the suite.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections import Counter
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import PyflowCheckpoint, parse_checkpoint

from workhorse_workflows.research import workflow as research
from workhorse_workflows.research.schemas import (
    Collected,
    DryRun,
    Job,
    JobWatch,
    RecordResult,
    RepoSetup,
)

PROGRAM_DIR = "programs/alpha"

#: What the temp program declares it can hold. Real numbers, because `check_envelope`
#: is not substituted — a design over these is rescoped by the workflow's own
#: arithmetic rather than by a stand-in that was told to say no.
PROGRAM_YML = (
    "code_root: src\n"
    "result_branch: alpha/auto\n"
    "goal: prove the loop drives\n"
    "min_containment: premium\n"
    "envelope_ram_gb: 32\n"
    "envelope_cpus: 8\n"
)


# --------------------------------------------------------------------------- fixtures


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _program_repo(root: Path) -> Path:
    """A committed git repo holding one well-formed research program."""
    repo = root / "repo"
    (repo / PROGRAM_DIR).mkdir(parents=True)
    (repo / "src").mkdir()
    (repo / PROGRAM_DIR / "program.yml").write_text(PROGRAM_YML)
    (repo / PROGRAM_DIR / "README.md").write_text("# Alpha\n\n## Ladder\n\n- G1\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "seed")
    return repo


class _Agent:
    """A scripted agent backend, keyed by prompt stem.

    Each entry is the list of replies that prompt returns, in order; the last one
    repeats, so a test that loops N times on one prompt states the reply once. Every
    call is recorded, which is how the counters are asserted: the number of times
    `design-experiment` ran IS the rework counter, observed from outside.
    """

    def __init__(self, script: dict[str, list[dict[str, Any]]]) -> None:
        self.script = {stem: list(replies) for stem, replies in script.items()}
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        self.calls.append(node.id)
        self.args.append(ctx.as_dict())
        replies = self.script.get(node.id)
        if not replies:
            raise AssertionError(f"no scripted reply for {node.id!r} (calls: {self.calls})")
        reply = replies.pop(0) if len(replies) > 1 else replies[0]
        return f"(scripted) {node.prompt}", reply

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for call, a in zip(self.calls, self.args) if call == stem]


class _Nodes:
    """The measurement half, scripted exactly the way the agent is.

    These four nodes are the only ones that would touch a real detached process, and
    they are unit-tested for real in `test_measure.py`. Here they are the *inputs* to a
    routing decision: a `Collected(outcome="crash", fault_locus="tooling")` is how a
    test states "the apparatus broke" without breaking an apparatus.

    A stem with no script gets the healthy default, so a test that is about the rework
    cap says nothing about jobs at all.
    """

    def __init__(self, **script: list[Any]) -> None:
        self.script = {name: list(replies) for name, replies in script.items()}
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    def _node(self, name: str, default: Any) -> Any:
        def run(logger: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            self.args.append(kwargs)
            replies = self.script.get(name)
            reply = default if not replies else (
                replies.pop(0) if len(replies) > 1 else replies[0]
            )
            # A reply may be a function of the call's arguments, which is how a test
            # names a path — a job's `wake` file — that only exists once the run has
            # chosen the job directory.
            return reply(kwargs) if callable(reply) else reply

        return run

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, name: str) -> list[dict[str, Any]]:
        return [a for call, a in zip(self.calls, self.args) if call == name]

    def overrides(self, repo: Path) -> dict[str, Any]:
        return {
            # In-place mode — what `clone_repo` does when a checkout is already in
            # front of it — is this return plus `allow_all_directories()`, which writes
            # `safe.directory=*` into the developer's **global** git config. That is
            # the container's bind-mount concession, and not something a test may do to
            # a laptop; the override is the half that is the behaviour.
            "clone_repo": lambda logger, repo_dir="", repo_url="", repo_branch="main": (
                RepoSetup(repo_dir=str(repo))
            ),
            "dry_run": self._node("dry_run", DryRun(ok=True, exit_code=0)),
            "submit_job": self._node(
                "submit_job",
                lambda kw: Job(
                    submitted=True,
                    job_dir=kw.get("job_dir", ""),
                    wake_path=str(Path(kw.get("job_dir", ".")) / "wake"),
                ),
            ),
            "watch_job": self._node("watch_job", JobWatch(action="collect")),
            "collect_job": self._node(
                "collect_job",
                Collected(outcome="ok", result_status="ok", n_completed=8, n_planned=8),
            ),
            "kill_job": self._node("kill_job", Collected(outcome="crash", wall_s=1.0)),
        }


class _Parked(Exception):
    """The run reached an operator gate — raised in place of blocking on it.

    An `Await` is not an ending, so a test cannot assert one by catching a failure. The
    driver writes the checkpoint and the gate file *before* it waits, so cutting the
    wait short leaves everything an assertion needs on disk and proves the park was
    reached rather than merely returned.
    """

    def __init__(self, path: Path, text: str) -> None:
        super().__init__(f"parked on {path}")
        self.path = path
        self.text = text


class _Run:
    """What one drive left behind, snapshotted before its tempdir goes away."""

    def __init__(self, **fields: Any) -> None:
        self.result: Any = fields.get("result")
        self.error: WorkflowFailed | None = fields.get("error")
        self.parked: _Parked | None = fields.get("parked")
        self.agent: _Agent = fields["agent"]
        self.nodes: _Nodes = fields["nodes"]
        self.waited: list[Path] = fields["waited"]
        self.checkpoints: list[dict[str, Any]] = fields["checkpoints"]
        self.branches: list[str] = fields["branches"]
        self.ledger: str = fields["ledger"]

    @property
    def blocked_text(self) -> str:
        if self.parked is None:
            raise AssertionError(
                f"expected an operator block; ended {self.result!r} / {self.error!r}"
            )
        return self.parked.text


def _env(root: Path, repo: Path, agent: _Agent, nodes: _Nodes) -> RunEnv:
    """The run's dependencies, handed over rather than patched in."""
    writer = ArtifactWriter("research", root / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        # Where the engine would render prompts from. No prompt is rendered here (the
        # scripted agent stands in for the turn), but the real directory keeps the paths
        # in the recorded steps honest.
        workflow_dir=Path(research.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(),
        agent_runner=StubRunner(agent),
        nodes=research.workflow.override(**nodes.overrides(repo)),
    )


def _branches(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return out.stdout.split()


def _drive(
    script: dict[str, list[dict[str, Any]]],
    *,
    nodes: _Nodes | None = None,
    ledger: str = "",
    caps: dict[str, int] | None = None,
    answer: str = "",
    **inputs: Any,
) -> _Run:
    """Drive `Research` against a real repo until it terminates, parks, or halts.

    `caps` patches the `MAX_*` constants, which is how a budget is asserted: by
    *changing the constant*, which is only possible because there is one copy of it.
    `ledger` seeds the program's spend file, which is how a *prior run's* budget gets
    into a test without running one.

    `answer` is an operator who is *present*: the block writes it onto the gate and the
    wait returns, so the run resumes through the block instead of ending at it. Without
    it a block is the end of the drive, which is what most tests here want.
    """
    waited: list[Path] = []
    checkpoints: list[dict[str, Any]] = []
    real_write = ArtifactWriter.write_state_checkpoint

    def capture(self: Any, state: str, params: dict[str, Any], **kwargs: Any) -> Any:
        checkpoints.append({"engine": "pyflow", "state": state, "params": params, **kwargs})
        return real_write(self, state, params, **kwargs)

    def fake_wait(path: Path, **kwargs: Any) -> None:
        waited.append(Path(path))
        if Path(path).name == research.BLOCKED_NAME:
            text = Path(path).read_text() if Path(path).exists() else ""
            if answer:
                Path(path).write_text(f"{text}\n\n## Operator answer\n\n{answer}\n")
                return
            raise _Parked(Path(path), text)
        # A job's own `wake` file: the supervisor touched it, so the wait is over and
        # `await_result` re-enters and looks again. Nobody was asked anything.

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _program_repo(root)
        if ledger:
            (repo / PROGRAM_DIR / "ledger.yml").write_text(ledger)
        agent = _Agent(script)
        nodes = nodes or _Nodes()
        result: Any = None
        error: WorkflowFailed | None = None
        parked: _Parked | None = None
        with ExitStack() as stack:
            stack.enter_context(patch.object(pyflow_driver, "wait_for_answer", fake_wait))
            stack.enter_context(
                patch.object(ArtifactWriter, "write_state_checkpoint", capture)
            )
            for name, value in (caps or {}).items():
                stack.enter_context(patch.object(research, name, value))
            try:
                result = drive(
                    research.Research(program=PROGRAM_DIR, **inputs),
                    _env(root, repo, agent, nodes),
                )
            except _Parked as exc:
                parked = exc
            except WorkflowFailed as exc:
                error = exc
        ledger_file = repo / PROGRAM_DIR / "ledger.yml"
        return _Run(
            result=result,
            error=error,
            parked=parked,
            agent=agent,
            nodes=nodes,
            waited=waited,
            checkpoints=checkpoints,
            branches=_branches(repo),
            ledger=ledger_file.read_text() if ledger_file.exists() else "",
        )


def _run(script: dict[str, list[dict[str, Any]]], **kwargs: Any) -> _Run:
    """Drive to a clean terminal, or fail the test with whatever happened instead."""
    outcome = _drive(script, **kwargs)
    if outcome.error is not None:
        raise AssertionError(f"expected a clean terminal, halted: {outcome.error}")
    if outcome.parked is not None:
        raise AssertionError(f"expected a clean terminal, parked: {outcome.parked.text}")
    return outcome


def _parking(script: dict[str, list[dict[str, Any]]], **kwargs: Any) -> _Run:
    """Drive to an operator block, or fail the test with the ending it reached."""
    outcome = _drive(script, **kwargs)
    if outcome.parked is None:
        raise AssertionError(
            f"expected an operator block, ended {outcome.result!r} / {outcome.error!r}"
        )
    return outcome


#: The turns a gate needs when nothing about the science is under test.
GATE = {
    "select-next-gate": [
        {"gate_id": "G1", "gate_doc_path": f"{PROGRAM_DIR}/gates/G1.md"},
        {"gate_id": "none"},
    ],
    "design-experiment": [{"status": "ok", "memory_mb": 4000, "estimate_s": 600.0}],
    "build-experiment": [{"status": "ok", "command": ["python", "run.py"]}],
    "record-result": [{"status": "ok", "outcome": "PASS"}],
    "lead-goal-review": [{"verdict": "reached"}],
}


def _script(**overrides: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {**{stem: list(v) for stem, v in GATE.items()}, **overrides}


# --------------------------------------------------------------- the happy path


def test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal():
    """One full pass through the new graph: pick a gate, design it, build it, rehearse
    it at n=1, submit it, collect the artifact, judge it, record it, find the ladder
    exhausted, and let the lead declare the North star reached."""
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}))

    assert isinstance(outcome.result, RecordResult), outcome.result
    counts = outcome.agent.counts()
    assert counts["design-experiment"] == 1, counts
    assert counts["build-experiment"] == 1, counts
    assert counts["gate-check"] == 1, counts
    # The gate's record, then the goal's.
    assert counts["record-result"] == 2, counts
    # The measurement happened once, outside every turn, and was rehearsed first.
    assert outcome.nodes.counts() == Counter(
        {"dry_run": 1, "submit_job": 1, "watch_job": 1, "collect_job": 1}
    ), outcome.nodes.counts()


def test_the_measurement_never_runs_inside_the_reviewing_turn():
    """The defect this whole rewrite exists to remove.

    `check` used to re-run the experiment — 76 minutes of it — and record "the largest
    subset that fits" as a partial verdict. It now gets the artifact and nothing that
    would let it re-measure: no command, no job dir, and not even the progress file the
    designer wrote, which is what it must not be anchored on.
    """
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}))

    (args,) = outcome.agent.args_for("gate-check")
    assert set(args) == {"repo_dir", "program_dir", "gate_id", "gate_doc_path", "result"}
    # What it judges is the classified artifact, not a command it could have re-run.
    assert args["result"]["outcome"] == "ok", args
    assert args["result"]["n_completed"] == 8, args


def test_the_rework_carries_the_criteria_the_check_faulted():
    """`failed_criteria` crosses two transitions as JSON and arrives at the *scientist*
    as data — a rework is a protocol change, so it goes to the persona that owns the
    protocol and not to the one that owns the code."""
    outcome = _run(
        _script(
            **{
                "gate-check": [
                    {
                        "status": "needs_rework",
                        "failed_criteria": [
                            {
                                "criterion": "accuracy",
                                "expected": ">0.9",
                                "observed": "0.7",
                                "severity": "blocking",
                            }
                        ],
                        "notes": "under the bar",
                    },
                    {"status": "approved"},
                ]
            }
        )
    )

    counts = outcome.agent.counts()
    assert counts["gate-check"] == 2, counts
    # Two designs, one build per design: the rework re-entered the scientist.
    assert counts["design-experiment"] == 2, counts
    rework = outcome.agent.args_for("design-experiment")[1]
    assert rework["rework_notes"] == "under the bar", rework
    assert rework["rework_count"] == 1, rework
    assert rework["failed_criteria"][0]["criterion"] == "accuracy", rework


# ------------------------------------------------- who each failure is routed to


def test_a_crash_in_repo_code_goes_to_the_engineer_with_nobody_in_the_loop():
    """The locus decides the owner. A traceback whose deepest frame is in the repo is
    the one failure the loop is unambiguously equipped to fix itself, so it re-enters
    `build` — no operator, no science budget spent, and the reason travels."""
    nodes = _Nodes(
        collect_job=[
            Collected(
                outcome="crash",
                fault_locus="repo",
                exit_code=1,
                reason="ValueError: bad split",
                stderr_tail="Traceback…",
            ),
            Collected(outcome="ok", result_status="ok"),
        ]
    )
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}), nodes=nodes)

    counts = outcome.agent.counts()
    assert counts["build-experiment"] == 2, counts
    # The scientist was not disturbed: a crash is not a protocol problem.
    assert counts["design-experiment"] == 1, counts
    fix = outcome.agent.args_for("build-experiment")[1]
    assert fix["fix_count"] == 1, fix
    assert "ValueError: bad split" in fix["fix_reason"], fix


def test_a_tooling_fault_reaches_an_operator_immediately_and_names_the_component():
    """No number of engineer laps repairs workhorse, so the loop does not spend any.

    The block is immediate and it is the *first* thing that happens — the build budget
    is untouched, because there is nothing in this repo to fix.
    """
    nodes = _Nodes(
        collect_job=[
            Collected(
                outcome="crash",
                fault_locus="tooling",
                exit_code=1,
                reason="workhorse.job died",
            )
        ]
    )
    outcome = _parking(_script(**{"gate-check": [{"status": "approved"}]}), nodes=nodes)

    assert "**tooling** fault" in outcome.blocked_text, outcome.blocked_text
    assert "the measurement itself" in outcome.blocked_text, outcome.blocked_text
    assert "no science budget was spent" in outcome.blocked_text, outcome.blocked_text
    assert outcome.agent.counts()["build-experiment"] == 1, outcome.agent.counts()
    assert outcome.parked is not None
    assert outcome.parked.path.name == research.BLOCKED_NAME


def test_the_engineer_may_declare_a_tooling_fault_only_by_naming_what_is_broken():
    """The escape hatch, and its price. An engineer that can route its own hard
    problems to a human by calling them "tooling" has every reason to, so the component
    it names is published in the question the human reads."""
    outcome = _parking(
        _script(
            **{
                "build-experiment": [
                    {
                        "status": "blocked",
                        "fault_locus": "tooling",
                        "component": "ostler",
                        "notes": "the doc graph will not open",
                    }
                ]
            }
        )
    )

    assert "Component: ostler" in outcome.blocked_text, outcome.blocked_text
    assert "the doc graph will not open" in outcome.blocked_text, outcome.blocked_text
    # It never reached the runner: nothing was rehearsed and nothing was submitted.
    assert outcome.nodes.counts()["dry_run"] == 0, outcome.nodes.counts()


def test_the_operator_s_answer_reaches_the_state_it_released():
    """A block is a question, so the state that asked it has to be given the answer.

    It was not, and the shape of that bug is why this test exists: the resumed build was
    handed its own `notes` back as the reason it had been released, read the same
    evidence again, reached the same conclusion again, and blocked again — on a path
    that spends no budget, so nothing ever stopped it. What the operator wrote is the
    authorization; if it does not arrive, the block is a loop with a file in it.
    """
    outcome = _run(
        _script(
            **{
                "build-experiment": [
                    {
                        "status": "blocked",
                        "fault_locus": "tooling",
                        "component": "the runner's supervisor",
                        "notes": "the supervisor vanished without finalizing the job",
                    },
                    {"status": "ok", "command": ["python", "run.py"]},
                ],
                "gate-check": [{"status": "approved"}],
            }
        ),
        answer="The host rebooted; there is no defect. Do not raise this again — submit.",
    )

    turns = outcome.agent.args_for("build-experiment")
    assert len(turns) == 2, outcome.agent.counts()
    # The first ask had nothing on the gate yet; the second was told what came back.
    assert "The host rebooted" not in turns[0]["fix_reason"]
    assert "The host rebooted" in turns[1]["fix_reason"], turns[1]["fix_reason"]
    assert "Do not raise this again" in turns[1]["fix_reason"]
    # And the release was real: the run went on to rehearse and submit.
    assert outcome.nodes.counts()["dry_run"] == 1, outcome.nodes.counts()


def test_a_rehearsal_that_dies_under_the_runner_never_reaches_submission():
    """The n=1 dry run is through the *real* runner, and it is the handoff it tests.

    A command that works when typed and dies under the runner has failed the only test
    this state exists to run, and it fails before hours of CPU are spent rather than
    after.
    """
    nodes = _Nodes(
        dry_run=[
            DryRun(ok=False, exit_code=1, fault_locus="repo", reason="no such file: run.py"),
            DryRun(ok=True, exit_code=0),
        ]
    )
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}), nodes=nodes)

    assert outcome.nodes.counts()["dry_run"] == 2, outcome.nodes.counts()
    # One submission, after the rehearsal passed — not two, and not one before it.
    assert outcome.nodes.counts()["submit_job"] == 1, outcome.nodes.counts()
    fix = outcome.agent.args_for("build-experiment")[1]
    assert "the n=1 rehearsal failed" in fix["fix_reason"], fix


def test_an_estimate_with_no_probe_behind_it_goes_back_to_the_scientist():
    """The probe is the scientist's, so its absence is a design lap and not an
    engineering one — and the refusal is at submission, before the CPU is spent."""
    nodes = _Nodes(
        submit_job=[
            Job(submitted=False, fault_locus="design", error="the probe timed nothing"),
            Job(submitted=True, job_dir="/j", wake_path="/j/wake"),
        ]
    )
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}), nodes=nodes)

    counts = outcome.agent.counts()
    assert counts["design-experiment"] == 2, counts
    again = outcome.agent.args_for("design-experiment")[1]
    assert again["rescope_reason"] == "the probe timed nothing", again
    assert again["rescope_count"] == 1, again


def test_a_design_the_machine_cannot_hold_is_rescoped_without_a_person():
    """`check_envelope` is not substituted: the program declares 32 GB, the design asks
    for 64, and the workflow's own arithmetic sends it back to be rescoped. An
    experiment too big for the machine is a protocol to shrink, not an operator's
    problem and not a science failure."""
    outcome = _run(
        _script(
            **{
                "design-experiment": [
                    {"status": "ok", "memory_mb": 64_000, "estimate_s": 600.0},
                    {"status": "ok", "memory_mb": 4_000, "estimate_s": 600.0},
                ],
                "gate-check": [{"status": "approved"}],
            }
        )
    )

    counts = outcome.agent.counts()
    assert counts["design-experiment"] == 2, counts
    assert counts["build-experiment"] == 1, counts
    again = outcome.agent.args_for("design-experiment")[1]
    assert "64000" in again["rescope_reason"].replace(",", ""), again


def test_outgrowing_the_declared_resources_mid_run_is_the_scientist_s_to_rescope():
    """`over_resource` is neither a crash nor a miss: the protocol asked for less than
    it needed, which only the persona that declared the number can fix."""
    nodes = _Nodes(
        collect_job=[
            Collected(
                outcome="over_resource",
                kill_reason="memory",
                peak_rss_mb=8200.0,
                reason="peaked at 8200MB over its declared 4000MB",
            ),
            Collected(outcome="ok", result_status="ok"),
        ]
    )
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}), nodes=nodes)

    again = outcome.agent.args_for("design-experiment")[1]
    assert "8200MB" in again["rescope_reason"], again
    # Not the engineer's: the build was not asked to repair anything.
    assert outcome.agent.args_for("build-experiment")[1]["fix_reason"] == ""


# ------------------------------------------------------------- waiting and overrun


def test_the_wait_parks_on_the_job_s_own_wake_file_and_asks_nobody_anything():
    """Hours or days pass here, and no turn and no person is spent on them.

    The park is on the supervisor's `wake` file rather than an operator gate, so
    nothing is written for a human to answer and the wait ends on the supervisor's
    first touch.
    """
    nodes = _Nodes(
        watch_job=[
            lambda kw: JobWatch(
                action="wait",
                wake_path=str(Path(kw["job_dir"]) / "wake"),
                state="running",
            ),
            JobWatch(action="collect", state="finished"),
        ]
    )
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}), nodes=nodes)

    assert [p.name for p in outcome.waited] == ["wake"], outcome.waited
    assert outcome.nodes.counts()["watch_job"] == 2, outcome.nodes.counts()
    # No operator gate was ever written.
    assert not any(p.name == research.BLOCKED_NAME for p in outcome.waited)


def test_an_overrun_goes_to_the_engineer_and_keeping_going_costs_nothing_else():
    """Time is a bug signal, not a budget. A job past its estimate is triaged by the
    engineer rather than killed by a timeout, and keeping going re-enters the wait with
    the multiple already seen — so one threshold triages once."""
    nodes = _Nodes(
        watch_job=[
            JobWatch(action="triage", state="running", overrun_multiple=10.0),
            JobWatch(action="collect", state="finished"),
        ]
    )
    outcome = _run(
        _script(
            **{
                "gate-check": [{"status": "approved"}],
                "triage-overrun": [{"decision": "keep_going", "diagnosis": "it is slow"}],
            }
        ),
        nodes=nodes,
    )

    assert outcome.agent.counts()["triage-overrun"] == 1, outcome.agent.counts()
    assert outcome.nodes.counts()["kill_job"] == 0, outcome.nodes.counts()
    # The second watch carried the multiple the first one triaged.
    assert outcome.nodes.args_for("watch_job")[1]["seen_multiple"] == 10.0
    assert outcome.agent.args_for("triage-overrun")[0]["overrun_multiple"] == 10.0


def test_the_engineer_can_kill_a_runaway_job_and_the_gate_is_rebuilt():
    """The only way a job dies of time — an explicit engineering decision, with a
    diagnosis attached, that then routes as any other repair does."""
    nodes = _Nodes(
        watch_job=[
            JobWatch(action="triage", state="running", overrun_multiple=40.0),
            JobWatch(action="collect", state="finished"),
        ]
    )
    outcome = _run(
        _script(
            **{
                "gate-check": [{"status": "approved"}],
                "triage-overrun": [
                    {
                        "decision": "kill_and_fix",
                        "diagnosis": "the loader re-reads the corpus every step",
                        "fix_hint": "cache it",
                    }
                ],
            }
        ),
        nodes=nodes,
    )

    assert outcome.nodes.counts()["kill_job"] == 1, outcome.nodes.counts()
    fix = outcome.agent.args_for("build-experiment")[1]
    assert "killed at 40× its estimate" in fix["fix_reason"], fix
    assert "cache it" in fix["fix_reason"], fix


# ------------------------------------------------------------------- the budgets


def test_the_rework_cap_hands_the_gate_to_the_lead_and_does_not_stop_the_run():
    """An exhausted rework budget is a question, not an ending.

    The cap is asserted by *changing the constant*, which is only possible because
    there is one copy of it. What it buys is the lead: `max_reworks` is an apparatus
    verdict, and the only persona that can say whether the gate is worth a different
    shape is the one that owns the program's direction.
    """
    outcome = _parking(
        _script(
            **{
                "gate-check": [{"status": "needs_rework", "notes": "still under"}],
                "research-lead-review": [{"verdict": "new_direction"}],
                "define-new-direction": [{"status": "ok", "direction_name": "beta"}],
            }
        ),
        caps={"MAX_REWORKS": 1},
    )

    assert outcome.agent.counts()["gate-check"] == 2, outcome.agent.counts()
    review = outcome.agent.args_for("research-lead-review")[0]
    assert review["escalation"] == "max_reworks", review
    assert "measured and missed" in review["notes"], review
    assert "still under" in review["notes"], review


def test_the_build_fix_cap_hands_the_gate_to_the_lead_too():
    """Same shape, different owner upstream: three engineering repairs that never
    reached a measurement stop being "why did it crash" and become "is this gate worth
    another shape"."""
    nodes = _Nodes(
        collect_job=[Collected(outcome="crash", fault_locus="repo", reason="segfault")]
    )
    outcome = _parking(
        _script(
            **{
                "research-lead-review": [{"verdict": "new_direction"}],
                "define-new-direction": [{"status": "ok", "direction_name": "beta"}],
            }
        ),
        nodes=nodes,
        caps={"MAX_BUILD_FIXES": 1},
    )

    review = outcome.agent.args_for("research-lead-review")[0]
    assert review["escalation"] == "max_build_fixes", review
    assert "segfault" in review["notes"], review


def test_the_rescope_cap_hands_the_gate_to_the_lead():
    """A design that will not fit the machine twice over is not a rescope away from
    fitting; it is a gate the program has to reshape."""
    outcome = _parking(
        _script(
            **{
                "design-experiment": [
                    {"status": "ok", "memory_mb": 64_000, "estimate_s": 600.0}
                ],
                "research-lead-review": [{"verdict": "new_direction"}],
                "define-new-direction": [{"status": "ok", "direction_name": "beta"}],
            }
        ),
        caps={"MAX_RESCOPES": 1},
    )

    review = outcome.agent.args_for("research-lead-review")[0]
    assert review["escalation"] == "max_rescopes", review


def test_the_lead_review_cap_parks_on_an_operator_rather_than_ending_the_run():
    """No arm ends in `WorkflowFailed`, and this is the one that used to.

    Answering the block authorizes exactly one more review — the grant is what stops
    the resume from re-reading the same count and blocking again, which would be a loop
    with a human in it and worse than the give-up it replaced.
    """
    outcome = _parking(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True}
                ]
            }
        ),
        caps={"MAX_LEAD_REVIEWS": 0},
    )

    assert "research-lead reviews" in outcome.blocked_text, outcome.blocked_text
    assert "authorizes exactly one more review" in outcome.blocked_text
    assert outcome.agent.counts()["research-lead-review"] == 0, outcome.agent.counts()


def test_the_extension_cap_parks_instead_of_halting_the_program():
    """A program at the extension cap is usually deferring a verdict it could give, so
    the question goes to a person — and the run stays resumable rather than dying."""
    outcome = _parking(
        _script(
            **{
                "select-next-gate": [{"gate_id": "none"}],
                "lead-goal-review": [
                    {
                        "verdict": "extend",
                        "next_gate_title": "G9",
                        "next_gate_question": "does it hold at scale?",
                    }
                ],
            }
        ),
        caps={"MAX_EXTENSIONS": 0},
    )

    assert "extended itself 0 times" in outcome.blocked_text, outcome.blocked_text
    assert "G9" in outcome.blocked_text, outcome.blocked_text
    assert outcome.agent.counts()["extend-program"] == 0, outcome.agent.counts()


def test_the_extension_cap_counts_what_earlier_runs_spent():
    """The counters are program-scoped, not run-scoped. A program driven by six
    successive runs would otherwise spend the whole extension budget six times over,
    which makes the cap bound nothing."""
    outcome = _parking(
        _script(
            **{
                "select-next-gate": [{"gate_id": "none"}],
                "lead-goal-review": [{"verdict": "extend", "next_gate_title": "G9"}],
            }
        ),
        ledger="status: active\nextensions: 2\nlead_reviews: 0\n",
        caps={"MAX_EXTENSIONS": 2},
    )

    assert "extended itself 2 times" in outcome.blocked_text, outcome.blocked_text
    # And the lead was told its own spend before it judged.
    review = outcome.agent.args_for("lead-goal-review")[0]
    assert review["extensions_spent"] == 2, review


def test_extending_writes_the_spend_where_the_next_run_reads_it():
    """`record_spend` runs for real: the ledger the *next* run reads is the artifact
    that makes the cap survive a relaunch."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [{"gate_id": "none"}],
                "lead-goal-review": [
                    {"verdict": "extend", "next_gate_title": "G9"},
                    {"verdict": "reached"},
                ],
                "extend-program": [{"status": "ok", "new_gate_id": "G9"}],
            }
        )
    )

    assert "extensions: 1" in outcome.ledger, outcome.ledger
    assert "status: reached" in outcome.ledger, outcome.ledger


# ------------------------------------------------------- the lead, and the endings


def test_a_pre_existing_kill_reaches_the_lead_rather_than_dying():
    """A kill recorded by an earlier run is a verdict to review, not a reason to stop.

    `revive` is the autonomous arm: the lead decided the kill was wrong, the gate is
    re-scoped, and the loop continues with no person in it.
    """
    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                    {"gate_id": "none"},
                ],
                "research-lead-review": [{"verdict": "revive", "kill_was_correct": False}],
                "revive-gate": [{"status": "ok", "gate_id": "G1"}],
            }
        )
    )

    counts = outcome.agent.counts()
    assert counts["revive-gate"] == 1, counts
    assert isinstance(outcome.result, RecordResult), outcome.result


def test_a_new_direction_always_reaches_a_person_and_is_published_first():
    """Not because anything failed. A new direction discards a ladder somebody chose,
    which is precisely the decision nobody wants to find out about on Monday — and the
    work is already written and committed when the block lands, so answering costs a
    read rather than a re-run."""
    outcome = _parking(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True}
                ],
                "research-lead-review": [{"verdict": "new_direction"}],
                "define-new-direction": [
                    {
                        "status": "ok",
                        "direction_name": "sparse routing",
                        "core_question": "does routing beat width?",
                        "new_gates": ["H1", "H2"],
                    }
                ],
            }
        )
    )

    assert "sparse routing" in outcome.blocked_text, outcome.blocked_text
    assert "H1, H2" in outcome.blocked_text, outcome.blocked_text
    assert "alpha/auto" in outcome.branches, outcome.branches


def test_a_lead_verdict_the_loop_cannot_act_on_parks_instead_of_guessing():
    """The conservative else arm. An unreadable verdict is a question for a person, and
    the run waits with everything it had rather than picking an arm."""
    outcome = _parking(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True}
                ],
                "research-lead-review": [{"verdict": "maybe"}],
            }
        )
    )

    assert "no actionable verdict" in outcome.blocked_text, outcome.blocked_text


def test_an_impossible_verdict_ends_clean_and_concludes_the_program():
    """A recorded negative is a real result, so it is a `Done` — and it writes the
    ledger status that stops the *next* run until somebody re-authorizes it."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [{"gate_id": "none"}],
                "lead-goal-review": [{"verdict": "impossible"}],
            }
        )
    )

    assert isinstance(outcome.result, RecordResult), outcome.result
    assert "status: impossible" in outcome.ledger, outcome.ledger
    forced = outcome.agent.args_for("record-result")[0]
    assert forced["forced_outcome"] == research.GOAL_IMPOSSIBLE, forced


def test_a_banked_result_ends_clean_like_the_other_two_verdicts():
    """The fourth verdict, and the one a ladder-shaped program otherwise cannot
    express: the North star is not reached and nothing is ruled out, and yet the
    strongest result so far is worth shipping now."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [{"gate_id": "none"}],
                "lead-goal-review": [
                    {"verdict": "banked", "banked_result": "3.1× on the small split"}
                ],
            }
        )
    )

    assert "status: banked" in outcome.ledger, outcome.ledger


def test_a_concluded_program_needs_a_human_before_it_runs_again():
    """The one halt that is left, and it is at `setup()` — before any state runs.

    It is not a give-up: nothing was attempted, and the program is telling the launcher
    that a prior run already ended it. `reauthorize` is the human in the loop.
    """
    outcome = _drive(
        _script(**{"select-next-gate": [{"gate_id": "none"}]}),
        ledger="status: banked\nextensions: 0\nlead_reviews: 0\n",
    )

    assert outcome.error is not None, outcome.result
    assert "banked" in str(outcome.error), outcome.error
    assert outcome.agent.calls == [], outcome.agent.calls


# ------------------------------------------------------------ the checkpoint


def test_the_checkpoint_carries_the_counters_an_operator_would_edit():
    """The counters travel as one `Budget`, and the checkpoint holds its JSON
    projection — a legible object under `params.budget`, not a repr to decode."""
    outcome = _run(
        _script(
            **{
                "gate-check": [
                    {"status": "needs_rework", "notes": "again"},
                    {"status": "approved"},
                ]
            }
        )
    )

    checks = [cp["params"] for cp in outcome.checkpoints if cp["state"] == "check"]
    assert [cp["budget"]["reworks"] for cp in checks] == [0, 1], checks
    assert checks[0]["budget"] == {
        "reworks": 0,
        "build_fixes": 0,
        "rescopes": 0,
        "lead_reviews": 0,
        "extensions": 0,
        "lead_review_grants": 0,
        "extension_grants": 0,
    }
    # And it is plain JSON: every transition parameter is a str/int/list/dict, which is
    # what lets `coerce_params` revalidate it back into a `Budget` and a
    # `list[FailedCriterion]` on the way in.
    json.dumps(outcome.checkpoints)


def test_a_resume_rebuilds_the_budget_from_the_checkpoint():
    """The other half, and the one serialising alone cannot prove.

    `Budget` leaves as JSON and has to come back as a *model*: `check` reads
    `budget.reworks`, so a resume that handed it the raw dict would fail on an
    attribute rather than on the science. The checkpoint used here is the one the
    engine really wrote, taken through `json.dumps` and `read_resume` exactly the way a
    relaunch takes it off disk.
    """
    seen: list[dict[str, Any]] = []
    real_write = ArtifactWriter.write_state_checkpoint

    def capture(self: Any, state: str, params: dict[str, Any], **kwargs: Any) -> Any:
        seen.append({"engine": "pyflow", "state": state, "params": params, **kwargs})
        return real_write(self, state, params, **kwargs)

    reworking = {
        "design-experiment": [{"status": "ok", "memory_mb": 4000, "estimate_s": 600.0}],
        "build-experiment": [{"status": "ok", "command": ["python", "run.py"]}],
        "gate-check": [{"status": "needs_rework", "notes": "again"}],
        "record-result": [{"status": "ok"}],
        "research-lead-review": [{"verdict": "revive"}],
        "revive-gate": [{"status": "ok"}],
        "select-next-gate": [{"gate_id": "none"}],
        "lead-goal-review": [{"verdict": "reached"}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _program_repo(root)
        first = _Agent(
            {
                **reworking,
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md"},
                    {"gate_id": "none"},
                ],
            }
        )
        with (
            patch.object(ArtifactWriter, "write_state_checkpoint", capture),
            patch.object(research, "MAX_REWORKS", 2),
        ):
            drive(
                research.Research(program=PROGRAM_DIR),
                _env(root, repo, first, _Nodes()),
            )

        mid = parse_checkpoint(
            json.dumps([c for c in seen if c["state"] == "check"][1])
        )
        # The reader accepts either engine's checkpoint; a pyflow run writes the pyflow
        # one, and only that arm carries the state's arguments.
        assert isinstance(mid, PyflowCheckpoint)
        assert mid.params["budget"]["reworks"] == 1, mid.params

        second = _Agent(dict(reworking))
        resume = read_resume(mid)
        with patch.object(research, "MAX_REWORKS", 2):
            drive(
                research.Research(**resume.inputs),
                _env(root, repo, second, _Nodes()),
                resume,
            )

    # One more rework and then the cap. A budget that had come back as zero — or as a
    # dict `check` could not read `.reworks` off — would have spent three checks here
    # instead of two, so the count IS the assertion that the model was rebuilt.
    counts = second.counts()
    assert counts["gate-check"] == 2, counts
    assert counts["research-lead-review"] == 1, counts


def test_publishing_commits_the_gate_onto_the_result_branch():
    """`publish_results` runs for real: the run leaves a commit on `alpha/auto`."""
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}))

    assert "alpha/auto" in outcome.branches, outcome.branches
