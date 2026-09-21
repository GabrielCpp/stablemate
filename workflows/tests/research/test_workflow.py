"""End-to-end drives of the `research` state machine (`research/workflow.py`)."""
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

PROGRAM_YML = (
    "code_root: src\n"
    "result_branch: alpha/auto\n"
    "goal: prove the loop drives\n"
    "min_containment: premium\n"
    "envelope_ram_gb: 32\n"
    "envelope_cpus: 8\n"
)




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
    _install_commit_msg_hook(repo)
    return repo


def _install_commit_msg_hook(repo: Path) -> None:
    """Reject a git subject whose `type(scope):` scope is not lowercase."""
    hooks_dir = repo / ".git" / "hooks"
    hook = hooks_dir / "commit-msg"
    hook.write_text(
        "#!/usr/bin/env python3\n"
        "import re, sys\n"
        "subject = open(sys.argv[1]).readline()\n"
        "sys.exit(0 if re.match(r'\\w+(\\([a-z0-9][a-z0-9/-]*\\))?: ', subject) else 1)\n"
    )
    hook.chmod(0o755)


class _Agent:
    """A scripted agent backend, keyed by prompt stem."""

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
    """The measurement half, scripted exactly the way the agent is."""

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
            return reply(kwargs) if callable(reply) else reply

        return run

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, name: str) -> list[dict[str, Any]]:
        return [a for call, a in zip(self.calls, self.args) if call == name]

    def overrides(self, repo: Path) -> dict[str, Any]:
        return {
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
    """The run reached an operator gate — raised in place of blocking on it."""

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
        self.subjects: list[str] = fields["subjects"]
        self.ledger: str = fields["ledger"]
        self.history: list[dict[str, Any]] = fields.get("history", [])

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
    readme: str = "",
    makefile: str = "",
    uncommitted_files: dict[str, str] | None = None,
    **inputs: Any,
) -> _Run:
    """Drive `Research` against a real repo until it terminates, parks, or halts."""
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

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _program_repo(root)
        if ledger:
            (repo / PROGRAM_DIR / "ledger.yml").write_text(ledger)
        if readme:
            (repo / PROGRAM_DIR / "README.md").write_text(readme)
        if makefile:
            (repo / "Makefile").write_text(makefile)
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "chore: add Makefile")
        for rel_path, content in (uncommitted_files or {}).items():
            path = repo / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
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
        history_file = repo / PROGRAM_DIR / "history.jsonl"
        history = (
            [json.loads(line) for line in history_file.read_text().splitlines() if line]
            if history_file.exists()
            else []
        )
        return _Run(
            result=result,
            error=error,
            parked=parked,
            agent=agent,
            nodes=nodes,
            waited=waited,
            checkpoints=checkpoints,
            branches=_branches(repo),
            subjects=subprocess.check_output(
                ["git", "log", "--format=%s"], cwd=repo, text=True
            ).splitlines(),
            ledger=ledger_file.read_text() if ledger_file.exists() else "",
            history=history,
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


GATE = {
    "select-next-gate": [
        {"gate_id": "G1", "gate_doc_path": f"{PROGRAM_DIR}/gates/G1.md"},
        {"gate_id": "none"},
    ],
    "design-experiment": [{"status": "ok", "memory_mb": 4000, "estimate_s": 600.0}],
    "build-experiment": [{"status": "ok", "command": ["python", "run.py"]}],
    "code-review-experiment": [{"status": "approve"}],
    "record-result": [{"status": "ok", "outcome": "PASS"}],
    "lead-goal-review": [{"verdict": "reached"}],
    "program-review": [{"verdict": "continue"}],
    "program-recharter": [{"status": "written"}],
}


def _script(**overrides: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {**{stem: list(v) for stem, v in GATE.items()}, **overrides}




def test_a_gate_designed_built_measured_and_approved_drives_the_program_to_its_goal():
    """One full pass through the new graph: pick a gate, design it, build it, rehearse it at n=1, submit it, collect the artifact, judge it, record it, find the ladder exhausted, and let the lead declare the North star reached."""
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}))

    assert isinstance(outcome.result, RecordResult), outcome.result
    counts = outcome.agent.counts()
    assert counts["design-experiment"] == 1, counts
    assert counts["build-experiment"] == 1, counts
    assert counts["gate-check"] == 1, counts
    assert counts["record-result"] == 2, counts
    assert outcome.nodes.counts() == Counter(
        {"dry_run": 1, "submit_job": 1, "watch_job": 1, "collect_job": 1}
    ), outcome.nodes.counts()


def test_the_measurement_never_runs_inside_the_reviewing_turn():
    """The defect this whole rewrite exists to remove."""
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}))

    (args,) = outcome.agent.args_for("gate-check")
    assert set(args) == {"repo_dir", "program_dir", "gate_id", "gate_doc_path", "result"}
    assert args["result"]["outcome"] == "ok", args
    assert args["result"]["n_completed"] == 8, args


def test_the_rework_carries_the_criteria_the_check_faulted():
    """`failed_criteria` crosses two transitions as JSON and arrives at the *scientist* as data — a rework is a protocol change, so it goes to the persona that owns the protocol and not to the one that owns the code."""
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
    assert counts["design-experiment"] == 2, counts
    rework = outcome.agent.args_for("design-experiment")[1]
    assert rework["rework_notes"] == "under the bar", rework
    assert rework["rework_count"] == 1, rework
    assert rework["failed_criteria"][0]["criterion"] == "accuracy", rework




def test_a_crash_in_repo_code_goes_to_the_engineer_with_nobody_in_the_loop():
    """The locus decides the owner."""
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
    assert counts["design-experiment"] == 1, counts
    fix = outcome.agent.args_for("build-experiment")[1]
    assert fix["fix_count"] == 1, fix
    assert "ValueError: bad split" in fix["fix_reason"], fix


def test_a_tooling_fault_reaches_an_operator_immediately_and_names_the_component():
    """No number of engineer laps repairs workhorse, so the loop does not spend any."""
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
    """The escape hatch, and its price."""
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
    assert outcome.nodes.counts()["dry_run"] == 0, outcome.nodes.counts()


def test_a_blocked_design_goes_to_the_lead_and_never_reaches_the_engineer():
    """The scientist is told to report `blocked` rather than design around a gate that contradicts the program, and the workflow used to forward that to `build` anyway."""
    outcome = _parking(
        _script(
            **{
                "design-experiment": [
                    {"status": "blocked", "notes": "Phase B has only 1,779 of the slots"}
                ],
                "research-lead-review": [{"verdict": "unknown"}],
            }
        )
    )

    counts = outcome.agent.counts()
    assert counts["build-experiment"] == 0, counts
    assert outcome.nodes.counts()["dry_run"] == 0, outcome.nodes.counts()
    assert outcome.nodes.counts()["submit_job"] == 0, outcome.nodes.counts()
    review = outcome.agent.args_for("research-lead-review")[0]
    assert review["escalation"] == "design_blocked", review
    assert "1,779" in review["notes"], review
    assert [h["event"] for h in outcome.history if h["gate_id"] == "G1"][:2] == [
        "gate_selected", "design_blocked",
    ], outcome.history
    assert outcome.checkpoints[-1]["params"]["budget"]["build_fixes"] == 0


def test_a_recharter_ordered_for_a_blocked_design_still_reaches_the_lead():
    """A design refusal and an unresolvable target are two different questions, and a program review can be right about one while the other stands."""
    outcome = _parking(
        _script(
            **{
                "design-experiment": [
                    {"status": "blocked", "notes": "amendments regress G1 and G2"}
                ],
                "program-review": [
                    {"verdict": "recharter", "reason": "target unresolvable on this split"}
                ],
                "program-recharter": [
                    {
                        "status": "written",
                        "new_target": {
                            "metric": "resolved",
                            "threshold": ">= 220/400",
                            "threshold_count": 220,
                            "n": 400,
                            "baseline_count": 200,
                            "seeds": [0, 1, 2],
                            "why_resolvable": "2 SE",
                        },
                    }
                ],
                "research-lead-review": [{"verdict": "unknown"}],
            }
        )
    )

    counts = outcome.agent.counts()
    assert counts["program-recharter"] == 1, counts
    assert counts["research-lead-review"] == 1, counts
    review = outcome.agent.args_for("research-lead-review")[0]
    assert review["escalation"] == "design_blocked", review
    assert "regress" in review["notes"], review
    assert counts["design-experiment"] == 1, counts


def test_a_revived_block_tells_the_reviser_what_the_gate_was_blocked_on():
    """A gate revived after a block is waiting on something, and only the block says what."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G2", "gate_doc_path": f"{PROGRAM_DIR}/gates/G2.md"},
                    {"gate_id": "none"},
                ],
                "design-experiment": [
                    {"status": "blocked", "notes": "the training pools G2 needs are not built"},
                    {"status": "ok", "memory_mb": 4000, "estimate_s": 600.0},
                ],
                "research-lead-review": [{"verdict": "revive", "apparatus_fix": "build pools"}],
                "revive-gate": [
                    {"status": "reopened", "gate_id": "G2", "prerequisite_gate_id": "G1b"}
                ],
                "gate-check": [{"status": "approved"}],
            }
        )
    )

    revived = outcome.agent.args_for("revive-gate")
    assert len(revived) == 1, outcome.agent.counts()
    assert revived[0]["escalation"] == "design_blocked", revived
    assert "training pools" in revived[0]["notes"], revived
    events = [(h["event"], h.get("note", "")) for h in outcome.history]
    assert any(e == "revive" and "G1b" in note for e, note in events), events


def test_a_blocked_build_goes_to_the_lead_without_touching_the_runner():
    """Same owner from the engineer's side: a prerequisite that is not on disk is not repaired by another build lap, and rehearsing whatever partial script exists proves nothing about the measurement."""
    outcome = _parking(
        _script(
            **{
                "build-experiment": [
                    {
                        "status": "blocked",
                        "command": [],
                        "dry_run_command": ["bash", "admission.sh"],
                        "notes": "six prerequisite files are missing",
                    }
                ],
                "research-lead-review": [{"verdict": "unknown"}],
            }
        )
    )

    assert outcome.nodes.counts()["dry_run"] == 0, outcome.nodes.counts()
    assert outcome.nodes.counts()["submit_job"] == 0, outcome.nodes.counts()
    review = outcome.agent.args_for("research-lead-review")[0]
    assert review["escalation"] == "build_blocked", review
    assert "six prerequisite files" in review["notes"], review
    assert outcome.agent.counts()["build-experiment"] == 1, outcome.agent.counts()


def test_a_build_with_no_command_is_repaired_before_anything_is_rehearsed():
    """An `ok` build that names no command has nothing a rehearsal could prove; it is the engineer's lap either way, taken now rather than after a wasted dry run."""
    outcome = _run(
        _script(
            **{
                "build-experiment": [
                    {"status": "ok", "command": [], "dry_run_command": ["true"]},
                    {"status": "ok", "command": ["python", "run.py"]},
                ],
                "gate-check": [{"status": "approved"}],
            }
        )
    )

    assert outcome.agent.counts()["build-experiment"] == 2, outcome.agent.counts()
    assert outcome.nodes.counts()["dry_run"] == 1, outcome.nodes.counts()
    fixes = [h for h in outcome.history if h["event"] == "build_fix"]
    assert len(fixes) == 1 and "no command" in fixes[0]["note"], outcome.history


def test_the_operator_s_answer_reaches_the_state_it_released():
    """A block is a question, so the state that asked it has to be given the answer."""
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
    assert "The host rebooted" not in turns[0]["fix_reason"]
    assert "The host rebooted" in turns[1]["fix_reason"], turns[1]["fix_reason"]
    assert "Do not raise this again" in turns[1]["fix_reason"]
    assert outcome.nodes.counts()["dry_run"] == 1, outcome.nodes.counts()


def test_a_dirty_lint_gate_is_repaired_before_the_rehearsal_runs():
    """The lint/test gate is deterministic and runs for real — a Makefile target that actually fails routes back to the engineer with no rehearsal spent, the same way a failed rehearsal itself does."""
    outcome = _parking(
        _script(
            **{
                "research-lead-review": [{"verdict": "new_direction"}],
                "define-new-direction": [{"status": "ok", "direction_name": "beta"}],
            }
        ),
        makefile="lint:\n\texit 1\n",
        caps={"MAX_BUILD_FIXES": 1},
    )

    turns = outcome.agent.args_for("build-experiment")
    assert len(turns) == 2, outcome.agent.counts()
    assert "the lint gate failed" in turns[1]["fix_reason"], turns[1]
    assert outcome.nodes.counts()["dry_run"] == 0, outcome.nodes.counts()
    review = outcome.agent.args_for("research-lead-review")[0]
    assert review["escalation"] == "max_build_fixes", review


def test_a_code_review_verdict_of_revise_is_repaired_before_the_rehearsal_runs():
    """A build that passes the deterministic gate clean can still be told to revise by the code-review turn — a spec-conformance bug lint and tests cannot see — and that routes back to the engineer exactly as a dirty gate does, before any CPU is spent on a rehearsal."""
    outcome = _run(
        _script(
            **{
                "build-experiment": [
                    {"status": "ok", "command": ["python", "run.py"]},
                    {"status": "ok", "command": ["python", "run.py"]},
                ],
                "code-review-experiment": [
                    {"status": "revise", "findings": "the control isn't shuffled"},
                    {"status": "approve"},
                ],
                "gate-check": [{"status": "approved"}],
            }
        )
    )

    turns = outcome.agent.args_for("build-experiment")
    assert len(turns) == 2, outcome.agent.counts()
    assert "the control isn't shuffled" in turns[1]["fix_reason"], turns[1]
    assert outcome.nodes.counts()["dry_run"] == 1, outcome.nodes.counts()


def test_an_approved_build_s_code_files_are_committed_before_the_rehearsal_runs():
    """An engineer's turn writes `code_files` to disk but does not commit them, and a gate is entitled to refuse to run against an uncommitted tree (a reproducibility guard: pin the commit a run measured before trusting its result)."""
    outcome = _run(
        _script(
            **{
                "build-experiment": [
                    {
                        "status": "ok",
                        "command": ["python", "src/experiment.py"],
                        "code_files": ["src/experiment.py"],
                    }
                ],
                "gate-check": [{"status": "approved"}],
            }
        ),
        uncommitted_files={"src/experiment.py": "print('measure')\n"},
    )

    assert "feat(g1): build experiment" in outcome.subjects, outcome.subjects
    assert outcome.nodes.counts()["dry_run"] == 1, outcome.nodes.counts()


def test_a_rehearsal_that_dies_under_the_runner_never_reaches_submission():
    """The n=1 dry run is through the *real* runner, and it is the handoff it tests."""
    nodes = _Nodes(
        dry_run=[
            DryRun(ok=False, exit_code=1, fault_locus="repo", reason="no such file: run.py"),
            DryRun(ok=True, exit_code=0),
        ]
    )
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}), nodes=nodes)

    assert outcome.nodes.counts()["dry_run"] == 2, outcome.nodes.counts()
    assert outcome.nodes.counts()["submit_job"] == 1, outcome.nodes.counts()
    fix = outcome.agent.args_for("build-experiment")[1]
    assert "the n=1 rehearsal failed" in fix["fix_reason"], fix


def test_an_estimate_with_no_probe_behind_it_goes_back_to_the_scientist():
    """The probe is the scientist's, so its absence is a design lap and not an engineering one — and the refusal is at submission, before the CPU is spent."""
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
    """`check_envelope` is not substituted: the program declares 32 GB, the design asks for 64, and the workflow's own arithmetic sends it back to be rescoped."""
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
    """`over_resource` is neither a crash nor a miss: the protocol asked for less than it needed, which only the persona that declared the number can fix."""
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
    assert outcome.agent.args_for("build-experiment")[1]["fix_reason"] == ""




def test_the_wait_parks_on_the_job_s_own_wake_file_and_asks_nobody_anything():
    """Hours or days pass here, and no turn and no person is spent on them."""
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
    assert not any(p.name == research.BLOCKED_NAME for p in outcome.waited)


def test_an_overrun_goes_to_the_engineer_and_keeping_going_costs_nothing_else():
    """Time is a bug signal, not a budget."""
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
    assert outcome.nodes.args_for("watch_job")[1]["seen_multiple"] == 10.0
    assert outcome.agent.args_for("triage-overrun")[0]["overrun_multiple"] == 10.0


def test_the_engineer_can_kill_a_runaway_job_and_the_gate_is_rebuilt():
    """The only way a job dies of time — an explicit engineering decision, with a diagnosis attached, that then routes as any other repair does."""
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




def test_the_rework_cap_hands_the_gate_to_the_lead_and_does_not_stop_the_run():
    """An exhausted rework budget is a question, not an ending."""
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
    """Same shape, different owner upstream: three engineering repairs that never reached a measurement stop being "why did it crash" and become "is this gate worth another shape"."""
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
    """A design that will not fit the machine twice over is not a rescope away from fitting; it is a gate the program has to reshape."""
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
    """No arm ends in `WorkflowFailed`, and this is the one that used to."""
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


def test_one_answer_authorizes_a_lead_review_for_a_program_already_past_the_cap():
    """The spend is program-scoped and the grants are not: a run started on a ledger two reviews over the cap has to be let through by the one answer that says "one more", not re-park on it until the operator has answered once per review over."""
    released = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                    {"gate_id": "none"},
                ],
                "research-lead-review": [{"verdict": "revive", "kill_was_correct": False}],
                "revive-gate": [{"status": "ok", "gate_id": "G1"}],
            }
        ),
        ledger="status: active\nlead_reviews: 6\n",
        caps={"MAX_LEAD_REVIEWS": 4},
        answer="one more",
    )

    assert released.agent.counts()["research-lead-review"] == 1, released.agent.counts()
    assert len(released.waited) == 1, released.waited
    assert "lead_reviews: 7" in released.ledger, released.ledger


def test_the_extension_cap_parks_instead_of_halting_the_program():
    """A program at the extension cap is usually deferring a verdict it could give, so the question goes to a person — and the run stays resumable rather than dying."""
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
    """The counters are program-scoped, not run-scoped."""
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
    review = outcome.agent.args_for("lead-goal-review")[0]
    assert review["extensions_spent"] == 2, review


def test_extending_writes_the_spend_where_the_next_run_reads_it():
    """`record_spend` runs for real: the ledger the *next* run reads is the artifact that makes the cap survive a relaunch."""
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




def test_a_pre_existing_kill_reaches_the_lead_rather_than_dying():
    """A kill recorded by an earlier run is a verdict to review, not a reason to stop."""
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


KILLED = {
    "select-next-gate": [{"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True}],
}

RESOLVABLE_README = (
    "# Alpha\n\n## North star\n\n"
    "| Field | Value |\n|---|---|\n"
    "| Metric | resolved |\n| Dataset | bench (n=400) |\n"
    "| Threshold | >= 220/400 |\n| Baseline | 200/400 |\n"
    "| Seeds | {0, 1, 2} |\n| Deadline | 2027-01-01 |\n\n"
    "## Frozen target\n\n"
    "| Field | Value |\n|---|---|\n"
    "| Metric | resolved |\n| Dataset | bench (n=400) |\n"
    "| Threshold | >= 220/400 |\n| Baseline | 200/400 |\n"
    "| Seeds | {0, 1, 2} |\n| Deadline | 2027-01-01 |\n"
)


def test_a_new_direction_is_checked_in_code_and_parks_only_when_its_target_cannot_resolve():
    """The arm that always reached a person now reaches one only for cause."""
    outcome = _parking(
        _script(
            **KILLED,
            **{
                "research-lead-review": [{"verdict": "new_direction"}],
                "define-new-direction": [
                    {
                        "status": "ok",
                        "direction_name": "sparse routing",
                        "core_question": "does routing beat width?",
                        "new_gates": ["H1", "H2"],
                    }
                ],
                "program-recharter": [{"status": "written"}],
            },
        )
    )

    counts = outcome.agent.counts()
    assert counts["program-review"] == 1, counts
    assert counts["define-new-direction"] == 1, counts
    assert counts["program-recharter"] == 2, counts
    first, second = outcome.agent.args_for("program-recharter")
    assert "Frozen target" in first["resolvability_failure"], first
    assert "sparse routing" in first["review"]["reason"], first
    assert second["resolvability_failure"], second
    assert "not resolvable after 2 attempts" in outcome.blocked_text, outcome.blocked_text
    assert "alpha/auto" in outcome.branches, outcome.branches
    events = [h["event"] for h in outcome.history]
    assert events.count("recharter") == 2, events
    assert "new_direction" in events, events


def test_a_new_direction_with_a_resolvable_target_starts_with_nobody_in_the_loop():
    """The other half: the lead's new README carries a target the eval can resolve, the in-code check passes, and the loop takes the new ladder at once."""

    def writes_readme(kw: dict[str, Any]) -> Any:
        return None

    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                    {"gate_id": "none"},
                ],
                "research-lead-review": [{"verdict": "new_direction"}],
                "define-new-direction": [{"status": "ok", "direction_name": "routing"}],
            }
        ),
        readme=RESOLVABLE_README,
    )

    counts = outcome.agent.counts()
    assert counts["program-recharter"] == 0, counts
    assert isinstance(outcome.result, RecordResult), outcome.result




def test_a_kill_reaches_the_program_lead_before_the_gate_lead():
    """The program-level question is asked first, on computed evidence: the dossier is built with no model call and rendered into the review, and the gate lead sees the same dossier when the program lead waves the kill through."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md"},
                    {"gate_id": "none"},
                ],
                "gate-check": [{"status": "killed", "notes": "below threshold"}],
                "research-lead-review": [{"verdict": "revive"}],
                "revive-gate": [{"status": "ok"}],
            }
        )
    )

    calls = outcome.agent.calls
    assert calls.index("program-review") < calls.index("research-lead-review"), calls
    review = outcome.agent.args_for("program-review")[0]
    assert review["origin"] == "kill", review
    assert "Frozen target" in review["dossier"], review["dossier"]
    assert review["program_reviews_max"] == research.MAX_PROGRAM_REVIEWS, review
    lead = outcome.agent.args_for("research-lead-review")[0]
    assert lead["dossier"] == review["dossier"]
    assert outcome.agent.counts()["program-review"] == 2, outcome.agent.counts()
    assert outcome.agent.args_for("program-review")[1]["origin"] == "revive"
    assert "program_reviews: 2" in outcome.ledger, outcome.ledger
    events = [h["event"] for h in outcome.history]
    assert events.count("program_review") == 2, events
    assert "kill" in events and "revive" in events, events


def test_the_program_lead_can_bank_a_killed_program_from_the_kill():
    """`bank` is reachable from a kill, not only from an exhausted ladder — which is where a circling program never arrives."""
    outcome = _run(
        _script(
            **KILLED,
            **{
                "program-review": [{"verdict": "bank", "reason": "83/147 is shippable"}],
            },
        )
    )

    assert "status: banked" in outcome.ledger, outcome.ledger
    forced = outcome.agent.args_for("record-result")[0]
    assert forced["forced_outcome"] == research.GOAL_BANKED, forced
    assert outcome.agent.counts()["research-lead-review"] == 0


def test_a_stop_negative_verdict_records_the_program_impossible():
    outcome = _run(
        _script(**KILLED, **{"program-review": [{"verdict": "stop_negative"}]})
    )

    assert "status: impossible" in outcome.ledger, outcome.ledger
    assert [h["event"] for h in outcome.history][-1] == "goal"


def test_a_probe_order_is_written_and_the_ladder_is_read_again():
    """`probe_first` orders one cheap decisive measurement: the re-charter turn writes it, nothing is re-run, and `start` picks the ladder up with the probe on top."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                    {"gate_id": "none"},
                ],
                "program-review": [
                    {
                        "verdict": "probe_first",
                        "reason": "parents are mode-collapsed",
                        "probe": {"gate_id": "P1", "question": "is base sharper?"},
                    },
                    {"verdict": "continue"},
                ],
                "program-recharter": [{"status": "written", "probe_doc_path": "P1.md"}],
            }
        )
    )

    calls = outcome.agent.calls
    i = calls.index("program-recharter")
    assert calls[i - 1] == "program-review" and calls[i + 1] == "select-next-gate", calls
    args = outcome.agent.args_for("program-recharter")[0]
    assert args["review"]["probe"]["gate_id"] == "P1", args
    assert args["gate_template"].endswith("gate.md"), args
    assert "recharters: 0" in outcome.ledger, outcome.ledger
    probe = [h for h in outcome.history if h["event"] == "probe_ordered"]
    assert probe and probe[0]["gate_id"] == "P1", outcome.history


def test_a_probe_ordered_for_a_blocked_design_does_not_reach_the_lead_yet():
    """`probe_first` defers the gate-level question until the probe is scored -- it does not resolve anything about the blocked gate the way `recharter` does."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G3", "gate_doc_path": f"{PROGRAM_DIR}/gates/G3.md"},
                    {"gate_id": "none"},
                ],
                "design-experiment": [
                    {"status": "blocked", "notes": "the n=1 rehearsal wrote no result file"},
                ],
                "program-review": [
                    {
                        "verdict": "probe_first",
                        "reason": "measure before rebuilding",
                        "probe": {"gate_id": "P1", "question": "does A5' restore collect_prefix?"},
                    },
                ],
                "program-recharter": [{"status": "written", "probe_doc_path": "P1.md"}],
            }
        )
    )

    assert outcome.agent.counts()["research-lead-review"] == 0, outcome.agent.counts()
    assert outcome.agent.counts()["select-next-gate"] == 2, outcome.agent.counts()


def test_a_recharter_is_checked_in_code_and_spends_its_own_budget():
    """The lead's `why_resolvable` is prose and is never trusted: the written numbers are read back and the effect is compared to seed noise."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                    {"gate_id": "none"},
                ],
                "program-review": [
                    {"verdict": "recharter", "reason": "1.7 SE cannot be told"},
                    {"verdict": "continue"},
                ],
                "program-recharter": [
                    {
                        "status": "written",
                        "new_target": {
                            "metric": "resolved",
                            "threshold": ">= 220/400",
                            "threshold_count": 220,
                            "n": 400,
                            "baseline_count": 200,
                            "seeds": [0, 1, 2],
                            "why_resolvable": "2 SE",
                        },
                    }
                ],
            }
        )
    )

    assert outcome.agent.counts()["program-recharter"] == 1, outcome.agent.counts()
    assert "recharters: 1" in outcome.ledger, outcome.ledger
    assert [h for h in outcome.history if h["event"] == "recharter"], outcome.history


def test_a_recharter_whose_numbers_do_not_clear_seed_noise_is_retried_once_then_parked():
    outcome = _parking(
        _script(
            **KILLED,
            **{
                "program-review": [{"verdict": "recharter", "reason": "too noisy"}],
                "program-recharter": [
                    {
                        "status": "written",
                        "new_target": {
                            "metric": "resolved",
                            "threshold_count": 93,
                            "n": 147,
                            "baseline_count": 83,
                            "seeds": [0, 1, 2],
                            "why_resolvable": "trust me",
                        },
                    }
                ],
            },
        )
    )

    assert outcome.agent.counts()["program-recharter"] == 2, outcome.agent.counts()
    retry = outcome.agent.args_for("program-recharter")[1]
    assert "NOT resolvable" in retry["resolvability_failure"], retry
    assert "Supply a bigger eval" in outcome.blocked_text, outcome.blocked_text


def test_the_recharter_cap_parks_with_the_proposed_target():
    outcome = _parking(
        _script(
            **KILLED,
            **{
                "program-review": [
                    {
                        "verdict": "recharter",
                        "reason": "again",
                        "recharter": {"metric": "resolved", "dataset": "swe", "n": 300},
                    }
                ],
            },
        ),
        ledger="status: active\nrecharters: 2\n",
    )

    assert "re-chartered its frozen target 2 times" in outcome.blocked_text
    assert "resolved on swe" in outcome.blocked_text, outcome.blocked_text
    assert outcome.agent.counts()["program-recharter"] == 0


def test_an_operator_verdict_parks_on_the_lead_s_own_question():
    outcome = _parking(
        _script(
            **KILLED,
            **{
                "program-review": [
                    {
                        "verdict": "operator",
                        "operator_question": "Is the SWE-bench cache still on disk?",
                        "reason": "the dossier cannot say",
                    }
                ],
            },
        )
    )

    assert "SWE-bench cache" in outcome.blocked_text, outcome.blocked_text
    parked = outcome.checkpoints[-1]
    assert parked["state"] == "program_review", parked
    assert parked["params"]["budget"]["program_reviews"] == 1, parked


def test_a_program_verdict_the_loop_cannot_act_on_parks_instead_of_guessing():
    outcome = _parking(_script(**KILLED, **{"program-review": [{"verdict": "shrug"}]}))

    assert "no actionable verdict" in outcome.blocked_text, outcome.blocked_text


def test_the_program_review_cap_parks_and_an_answer_authorizes_one_more():
    outcome = _parking(_script(**KILLED), ledger="status: active\nprogram_reviews: 8\n")

    assert "program-level reviews" in outcome.blocked_text, outcome.blocked_text
    assert outcome.agent.counts()["program-review"] == 0

    released = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                    {"gate_id": "none"},
                ],
                "program-review": [{"verdict": "bank"}],
            }
        ),
        ledger="status: active\nprogram_reviews: 8\n",
        answer="one more",
    )
    assert released.agent.counts()["program-review"] == 1, released.agent.counts()
    assert "program_reviews: 9" in released.ledger, released.ledger


def test_one_answer_authorizes_a_program_review_for_a_program_already_past_the_cap():
    released = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
                    {"gate_id": "none"},
                ],
                "program-review": [{"verdict": "bank"}],
            }
        ),
        ledger="status: active\nprogram_reviews: 10\n",
        answer="one more",
    )

    assert released.agent.counts()["program-review"] == 1, released.agent.counts()
    assert len(released.waited) == 1, released.waited
    assert "program_reviews: 11" in released.ledger, released.ledger


def test_a_periodic_review_fires_after_enough_gates_and_the_clock_restarts():
    """No kill, no escalation: three passes in a row and `start` still asks the program lead whether the ladder is worth a fourth."""
    outcome = _run(
        _script(
            **{
                "select-next-gate": [
                    {"gate_id": "G1", "gate_doc_path": "g.md"},
                    {"gate_id": "G2", "gate_doc_path": "g.md"},
                    {"gate_id": "G3", "gate_doc_path": "g.md"},
                    {"gate_id": "none"},
                ],
                "gate-check": [{"status": "approved"}],
            }
        ),
        caps={"PROGRAM_REVIEW_EVERY": 2},
    )

    reviews = outcome.agent.args_for("program-review")
    assert [r["origin"] for r in reviews] == ["periodic"], reviews
    assert reviews[0]["gate_id"] == "G3", reviews
    assert outcome.agent.counts()["design-experiment"] == 3
    cycles = [
        cp["params"].get("budget", {}).get("gate_cycles", 0)
        for cp in outcome.checkpoints
        if cp["state"] == "start"
    ]
    assert cycles == [0, 1, 2, 1], cycles


def test_a_resume_rebuilds_the_program_review_s_parameters_from_the_checkpoint():
    """`program_review` carries a `LeadReview | None` and a list of criteria; a resume has to bring both back as models, and the `revive` arm reads the review."""
    seen: list[dict[str, Any]] = []
    real_write = ArtifactWriter.write_state_checkpoint

    def capture(self: Any, state: str, params: dict[str, Any], **kwargs: Any) -> Any:
        seen.append({"engine": "pyflow", "state": state, "params": params, **kwargs})
        return real_write(self, state, params, **kwargs)

    script = {
        **_script(),
        "select-next-gate": [
            {"gate_id": "G1", "gate_doc_path": "g.md", "program_killed": True},
            {"gate_id": "none"},
        ],
        "research-lead-review": [{"verdict": "revive", "evidence": "wrong metric"}],
        "revive-gate": [{"status": "ok"}],
    }
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        repo = _program_repo(root)
        with patch.object(ArtifactWriter, "write_state_checkpoint", capture):
            drive(research.Research(program=PROGRAM_DIR), _env(root, repo, _Agent(script), _Nodes()))
        at_revive = [c for c in seen if c["state"] == "program_review"][1]
        resume = read_resume(parse_checkpoint(json.dumps(at_revive)))
        second = _Agent(script)
        drive(research.Research(**resume.inputs), _env(root, repo, second, _Nodes()), resume)

    revived = second.args_for("revive-gate")
    assert revived and revived[0]["lead_review"]["evidence"] == "wrong metric", revived


def test_a_lead_verdict_the_loop_cannot_act_on_parks_instead_of_guessing():
    """The conservative else arm."""
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
    """A recorded negative is a real result, so it is a `Done` — and it writes the ledger status that stops the *next* run until somebody re-authorizes it."""
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
    """The fourth verdict, and the one a ladder-shaped program otherwise cannot express: the North star is not reached and nothing is ruled out, and yet the strongest result so far is worth shipping now."""
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
    """The one halt that is left, and it is at `setup()` — before any state runs."""
    outcome = _drive(
        _script(**{"select-next-gate": [{"gate_id": "none"}]}),
        ledger="status: banked\nextensions: 0\nlead_reviews: 0\n",
    )

    assert outcome.error is not None, outcome.result
    assert "banked" in str(outcome.error), outcome.error
    assert outcome.agent.calls == [], outcome.agent.calls




def test_the_checkpoint_carries_the_counters_an_operator_would_edit():
    """The counters travel as one `Budget`, and the checkpoint holds its JSON projection — a legible object under `params.budget`, not a repr to decode."""
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
        "program_reviews": 0,
        "recharters": 0,
        "gate_cycles": 0,
        "lead_review_grants": 0,
        "extension_grants": 0,
        "program_review_grants": 0,
    }
    json.dumps(outcome.checkpoints)


def test_a_resume_rebuilds_the_budget_from_the_checkpoint():
    """The other half, and the one serialising alone cannot prove."""
    seen: list[dict[str, Any]] = []
    real_write = ArtifactWriter.write_state_checkpoint

    def capture(self: Any, state: str, params: dict[str, Any], **kwargs: Any) -> Any:
        seen.append({"engine": "pyflow", "state": state, "params": params, **kwargs})
        return real_write(self, state, params, **kwargs)

    reworking = {
        "design-experiment": [{"status": "ok", "memory_mb": 4000, "estimate_s": 600.0}],
        "build-experiment": [{"status": "ok", "command": ["python", "run.py"]}],
        "code-review-experiment": [{"status": "approve"}],
        "gate-check": [{"status": "needs_rework", "notes": "again"}],
        "record-result": [{"status": "ok"}],
        "research-lead-review": [{"verdict": "revive"}],
        "revive-gate": [{"status": "ok"}],
        "select-next-gate": [{"gate_id": "none"}],
        "lead-goal-review": [{"verdict": "reached"}],
        "program-review": [{"verdict": "continue"}],
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

    counts = second.counts()
    assert counts["gate-check"] == 2, counts
    assert counts["research-lead-review"] == 1, counts


def test_publishing_commits_the_gate_onto_the_result_branch():
    """`publish_results` runs for real: the run leaves a commit on `alpha/auto`."""
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}))

    assert "alpha/auto" in outcome.branches, outcome.branches


def test_publishing_names_the_gate_and_program_verdict():
    """A research history must distinguish a gate pass from program closure."""
    outcome = _run(_script(**{"gate-check": [{"status": "approved"}]}))
    assert "docs(alpha): record G1 pass" in outcome.subjects
    assert any("record goal" in s for s in outcome.subjects)
    assert all(s.startswith("docs(alpha): ") for s in outcome.subjects if s != "seed")
