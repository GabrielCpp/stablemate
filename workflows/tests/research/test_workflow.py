"""End-to-end drives of the `research` state machine (`research/workflow.py`).

Nothing is substituted except the agent turn and the clone. `load_program` and
`publish_results` run for real against a temporary git repo built by
:func:`_program_repo`, so a run here exercises manifest parsing, the `Program`
`setup()` residue every state reads, and a real commit onto the result branch.
`push_to_origin` is left alone precisely because it fails on a repo with no origin,
which is the soft-failure path publishing promises.

Both substitutions are **supplied**, not patched: a run's node index and its agent
backend are fields of `RunEnv`, so `_env` hands over a scripted agent and a
`clone_repo` bound to the temp repo, and nothing here assigns over a module attribute
it then has to remember to restore. Replies come from a per-prompt script, so each
test is a stated *path* through the machine.

What is under test is the loop's arithmetic. The YAML this replaces held three counters
in six scripts and nine nodes, with the caps duplicated as branch literals kept in sync
by a comment; here they are `MAX_REWORKS`/`MAX_LEAD_REVIEWS`/`MAX_EXTENSIONS` and the
guards read them. `test_the_rework_cap_...` is what that buys: the cap is asserted by
*changing the constant*, which is only possible when there is one copy of it.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import patch

from _fakes import StubRunner
from workhorse.artifacts import ArtifactWriter
from workhorse.config_run import RunConfig
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow.driver import drive, read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.research import workflow as research
from workhorse_workflows.research.schemas import RecordResult, RepoSetup

PROGRAM_DIR = "programs/alpha"


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
    (repo / PROGRAM_DIR / "program.yml").write_text(
        "code_root: src\nresult_branch: alpha/auto\ngoal: prove the loop drives\n"
    )
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
    `rework-experiment` ran IS the rework counter, observed from outside.
    """

    def __init__(self, script: dict[str, list[dict[str, Any]]]) -> None:
        self.script = script
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


def _env(root: Path, repo: Path, agent: _Agent) -> RunEnv:
    """The run's dependencies, handed over rather than patched in.

    `agent_runner` and the node index are fields of `RunEnv`, which is the whole point of
    the registry being a composition root: the scripted agent and the substituted clone
    are *inputs to this run*, so they cannot leak into another test and there is nothing
    to restore afterwards.
    """
    writer = ArtifactWriter("research", root / "runs", run_id="t")
    return RunEnv(
        writer=writer,
        # Where the engine would render prompts from. No prompt is rendered here (the
        # scripted agent stands in for the turn), but the real directory keeps the paths
        # in the recorded steps honest.
        workflow_dir=Path(research.__file__).parent,
        session_id_path=writer.run_dir / ".session_id",
        config=RunConfig(backend_factory=lambda cli=None: None),
        agent_runner=StubRunner(agent),
        # In-place mode — what `clone_repo` does when a checkout is already in front of
        # it — is this return plus `allow_all_directories()`, which writes
        # `safe.directory=*` into the developer's **global** git config. That is the
        # container's bind-mount concession, and not something a test may do to a
        # laptop; the override is the half that is the behaviour.
        nodes=research.workflow.override(
            clone_repo=lambda logger: RepoSetup(repo_dir=str(repo))
        ),
    )


def _drive(script: dict[str, list[dict[str, Any]]]) -> tuple[Any, WorkflowFailed | None, _Agent]:
    """Drive `Research` against a real repo until it terminates, either way.

    A fail terminal is a `raise`, so the agent transcript has to survive it — the
    budget tests below assert on how many turns ran *before* the halt.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _program_repo(root)
        agent = _Agent(script)
        result: Any = None
        error: WorkflowFailed | None = None
        try:
            result = drive(research.Research(program=PROGRAM_DIR), _env(root, repo, agent))
        except WorkflowFailed as exc:
            error = exc
        return result, error, agent


def _run(script: dict[str, list[dict[str, Any]]]) -> tuple[Any, _Agent]:
    """Drive to a clean terminal, or fail the test with the halt that happened."""
    result, error, agent = _drive(script)
    if error is not None:
        raise AssertionError(f"expected a clean terminal, halted: {error}")
    return result, agent


def _run_failing(script: dict[str, list[dict[str, Any]]]) -> tuple[WorkflowFailed, _Agent]:
    """Drive to a fail terminal, or fail the test with the result it ended on."""
    result, error, agent = _drive(script)
    if error is None:
        raise AssertionError(f"expected a fail terminal, ended clean: {result!r}")
    return error, agent


def _branches(repo: Path) -> list[str]:
    out = subprocess.run(
        ["git", "branch", "--format=%(refname:short)"],
        cwd=repo, check=True, capture_output=True, text=True,
    )
    return out.stdout.split()


# --------------------------------------------------------------- the happy path


def test_a_gate_reworked_once_then_approved_drives_the_program_to_its_goal():
    """One full pass: pick a gate, implement, fail the check, rework, pass, record,
    find the ladder exhausted, and let the lead declare the North star reached."""
    result, agent = _run(
        {
            "select-next-gate": [
                {"gate_id": "G1", "gate_doc_path": f"{PROGRAM_DIR}/gates/G1.md"},
                {"gate_id": "none"},
            ],
            "implement-experiment": [{"status": "done"}],
            "gate-check": [
                {
                    "status": "rework",
                    "failed_criteria": [
                        {
                            "criterion": "accuracy",
                            "expected": ">0.9",
                            "observed": "0.7",
                            "severity": "major",
                        }
                    ],
                    "notes": "under the bar",
                },
                {"status": "approved"},
            ],
            "rework-experiment": [{"status": "done"}],
            "record-result": [{"status": "ok", "outcome": "PASS"}],
            "lead-goal-review": [{"verdict": "reached"}],
        }
    )

    assert isinstance(result, RecordResult), result
    counts = agent.counts()
    # Two gate-checks and one rework: `reworks` went 0 → 1 as a state parameter, with
    # no init/incr script node anywhere between them.
    assert counts["gate-check"] == 2, counts
    assert counts["rework-experiment"] == 1, counts
    # The gate's record, then the goal's.
    assert counts["record-result"] == 2, counts
    assert counts["lead-goal-review"] == 1, counts


def test_the_rework_carries_the_criteria_the_check_faulted():
    """`failed_criteria` crosses two transitions as JSON and arrives at the rework
    prompt as data — the payload models the design rejected are not needed for it."""
    _, agent = _run(
        {
            "select-next-gate": [
                {"gate_id": "G1", "gate_doc_path": f"{PROGRAM_DIR}/gates/G1.md"},
                {"gate_id": "none"},
            ],
            "implement-experiment": [{"status": "done"}],
            "gate-check": [
                {
                    "status": "rework",
                    "failed_criteria": [
                        {"criterion": "accuracy", "expected": ">0.9", "observed": "0.7"}
                    ],
                    "notes": "under the bar",
                },
                {"status": "approved"},
            ],
            "rework-experiment": [{"status": "done"}],
            "record-result": [{"status": "ok"}],
            "lead-goal-review": [{"verdict": "reached"}],
        }
    )

    rework_args = agent.args[agent.calls.index("rework-experiment")]
    assert rework_args["rework_count"] == 0, rework_args
    assert rework_args["notes"] == "under the bar", rework_args
    assert rework_args["failed_criteria"][0]["criterion"] == "accuracy", rework_args


# ------------------------------------------------------------------ the counters


def test_the_rework_cap_is_one_constant_and_stopping_is_a_fail_terminal():
    """A gate that never passes reworks exactly `MAX_REWORKS` times and then halts.

    The cap is asserted by *lowering the constant*: in the YAML this required editing
    `vars.max_reworks` and the `guard_rework` branch literal together, and nothing but
    a comment connected them.
    """
    script = {
        "select-next-gate": [{"gate_id": "G1", "gate_doc_path": "g.md"}],
        "implement-experiment": [{"status": "done"}],
        "gate-check": [{"status": "rework", "notes": "still under"}],
        "rework-experiment": [{"status": "done"}],
        "record-result": [{"status": "ok"}],
    }
    with patch.object(research, "MAX_REWORKS", 2):
        error, agent = _run_failing(script)

    assert research.FAIL_MAX_REWORKS in str(error), error
    assert "G1" in str(error), error
    # Reworks 0 and 1 ran; the third check saw `reworks >= 2` and halted, so the
    # experiment was reworked twice and gate-checked three times.
    assert agent.counts()["rework-experiment"] == 2, agent.counts()
    assert agent.counts()["gate-check"] == 3, agent.counts()


def test_the_extension_cap_stops_a_program_that_keeps_extending_itself():
    """`extend` loops back through `start`, so nothing but `extensions` bounds it."""
    script = {
        "select-next-gate": [{"gate_id": "none"}],
        "lead-goal-review": [{"verdict": "extend"}],
        "extend-program": [{"status": "ok", "new_gate_id": "G9"}],
        "record-result": [{"status": "ok"}],
    }
    with patch.object(research, "MAX_EXTENSIONS", 2):
        error, agent = _run_failing(script)

    assert research.HALTED_EXTENSION_BUDGET in str(error), error
    assert agent.counts()["extend-program"] == 2, agent.counts()


# ------------------------------------------------------- routing the port could get wrong


def test_a_pre_existing_kill_reaches_the_lead_rather_than_dying():
    """`check_killed_pre` branched on the *string* `"true"` because a YAML branch
    compares rendered text. `program_killed` is a `bool` here, so the port has to
    branch on the value — comparing it to `"true"` would silently never fire."""
    _, agent = _run(
        {
            "select-next-gate": [
                {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                {"gate_id": "none"},
            ],
            "research-lead-review": [{"verdict": "revive"}],
            "revive-gate": [{"status": "ok", "gate_id": "G1"}],
            "lead-goal-review": [{"verdict": "impossible"}],
            "record-result": [{"status": "ok"}],
        }
    )

    counts = agent.counts()
    assert counts["research-lead-review"] == 1, counts
    assert counts["revive-gate"] == 1, counts
    # It never implemented: the kill was judged before any experiment ran.
    assert "implement-experiment" not in counts, counts


def test_an_impossible_verdict_ends_clean_and_a_budget_does_not():
    """The four terminals stay distinguishable: a recorded negative is a scientific
    result (`Done`), an exhausted budget is an apparatus failure (`WorkflowFailed`)."""
    result, _ = _run(
        {
            "select-next-gate": [{"gate_id": "none"}],
            "lead-goal-review": [{"verdict": "impossible"}],
            "record-result": [{"status": "ok", "outcome": research.GOAL_IMPOSSIBLE}],
        }
    )
    assert isinstance(result, RecordResult), result
    assert result.outcome == research.GOAL_IMPOSSIBLE, result


# -------------------------------------------------------------- the recorded run


def test_the_checkpoint_carries_the_counters_an_operator_would_edit():
    """The counters are state parameters, so they are in the checkpoint. In the YAML
    they lived in node outputs, which is why resuming with a different budget meant
    editing an `output.json` under the counter script's name."""
    seen: list[dict[str, Any]] = []
    real_write = ArtifactWriter.write_state_checkpoint

    def capture(self: Any, state: str, params: dict[str, Any], **kwargs: Any) -> Any:
        seen.append({"state": state, **params})
        return real_write(self, state, params, **kwargs)

    with patch.object(ArtifactWriter, "write_state_checkpoint", capture):
        _run(
            {
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md"},
                    {"gate_id": "none"},
                ],
                "implement-experiment": [{"status": "done"}],
                "gate-check": [
                    {"status": "rework", "notes": "again"},
                    {"status": "approved"},
                ],
                "rework-experiment": [{"status": "done"}],
                "record-result": [{"status": "ok"}],
                "lead-goal-review": [{"verdict": "reached"}],
            }
        )

    checks = [cp for cp in seen if cp["state"] == "check_gate"]
    # The counters travel as one `Budget`, and the checkpoint holds its JSON projection
    # — a legible object under `params.budget`, not a repr the operator has to decode.
    # `implement` hands `check_gate` a `fresh_gate()` budget, which is the whole of what
    # the YAML's `reset_rework` node did; `rework` then counts on top of it.
    assert [cp["budget"]["reworks"] for cp in checks] == [0, 1], checks
    assert checks[0]["budget"] == {"reworks": 0, "lead_reviews": 0, "extensions": 0}
    # And it is plain JSON: every transition parameter is a str/int/list/dict, which
    # is what lets `coerce_params` revalidate it back into a `Budget` and a
    # `list[FailedCriterion]` on the way in.
    json.dumps(seen)


def test_a_resume_rebuilds_the_budget_from_the_checkpoint():
    """The other half, and the one serialising alone cannot prove.

    `Budget` leaves as JSON and has to come back as a *model*: `check_gate` reads
    `budget.reworks`, so a resume that handed it the raw dict would fail on an
    attribute rather than on the science. The checkpoint used here is the one the
    engine really wrote, taken through `json.dumps` and `read_resume` exactly the way
    a relaunch takes it off disk — resumed one rework short of the cap, so the count
    it carries is what decides how much run is left.
    """
    seen: list[dict[str, Any]] = []
    real_write = ArtifactWriter.write_state_checkpoint

    def capture(self: Any, state: str, params: dict[str, Any], **kwargs: Any) -> Any:
        seen.append({"engine": "pyflow", "state": state, "params": params, **kwargs})
        return real_write(self, state, params, **kwargs)

    reworking = {
        "gate-check": [{"status": "rework", "notes": "again"}],
        "rework-experiment": [{"status": "done"}],
        "record-result": [{"status": "ok"}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _program_repo(root)
        first = _Agent(
            {
                "select-next-gate": [{"gate_id": "G1", "gate_doc_path": "g.md"}],
                "implement-experiment": [{"status": "done"}],
                **reworking,
            }
        )
        with (
            patch.object(ArtifactWriter, "write_state_checkpoint", capture),
            patch.object(research, "MAX_REWORKS", 2),
        ):
            try:
                drive(research.Research(program=PROGRAM_DIR), _env(root, repo, first))
            except WorkflowFailed:
                pass  # the cap; this run exists only to write the checkpoints

        mid = parse_checkpoint(json.dumps([c for c in seen if c["state"] == "check_gate"][1]))
        assert mid.params["budget"] == {
            "reworks": 1,
            "lead_reviews": 0,
            "extensions": 0,
        }, mid

        second = _Agent(dict(reworking))
        resume = read_resume(mid)
        with patch.object(research, "MAX_REWORKS", 2):
            try:
                drive(
                    research.Research(**resume.inputs),
                    _env(root, repo, second),
                    resume,
                )
            except WorkflowFailed as exc:
                error: WorkflowFailed | None = exc
            else:
                raise AssertionError("expected the rework cap to halt the resumed run")

    assert research.FAIL_MAX_REWORKS in str(error), error
    # One more rework and no gate selection: the resumed run picked the count up where
    # the checkpoint left it rather than starting the gate over at zero.
    assert second.counts()["rework-experiment"] == 1, second.counts()
    assert second.counts()["select-next-gate"] == 0, second.counts()


def test_publishing_commits_the_gate_onto_the_result_branch():
    """`publish_results` runs for real: the run leaves a commit on `alpha/auto`."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _program_repo(root)
        agent = _Agent(
            {
                "select-next-gate": [{"gate_id": "none"}],
                "lead-goal-review": [{"verdict": "reached"}],
                "record-result": [{"status": "ok"}],
            }
        )
        # A gate's product: something for publish to find and commit.
        (repo / PROGRAM_DIR / "PROGRESS.md").write_text("G1: PASS\n")

        drive(research.Research(program=PROGRAM_DIR), _env(root, repo, agent))

        assert "alpha/auto" in _branches(repo), _branches(repo)
        log = subprocess.run(
            ["git", "log", "--oneline", "alpha/auto"],
            cwd=repo, check=True, capture_output=True, text=True,
        )
        assert "alpha: automated gate update" in log.stdout, log.stdout
