"""End-to-end tests for the `review` flow — the settlement gate, the loop, the operator.

Eighteen YAML nodes became nine states holding three loops that share one `apply-review`
turn: the bounded rework loop, the operator arm that re-enters at the top with a fresh
budget, and the non-blocking feedback pass. What is worth testing is which arm each verdict
takes, what makes each loop terminate, and — the one that matters most — that the apply
turn's *self-reported* status never decides anything.

**There are no seams here beyond the agent turn.** `resolve_review_context` really decodes a
real `plan-context.json` against a real `.code-workspace`, `stamp_specs` really stamps the
spec docs ostler then reads back, and `verify_review_resolution` really drives
`Ostler.settle_review` over a real `review-resolution.json`, verifying every cited artifact
against the filesystem. That last one is the anti-gaming gate the whole flow exists for, so
scripting it would have tested the state machine against a fiction.

The scripted agent is scripted the way `dev`'s is: it dispatches on the prompt's filename and
every handler leaves behind the artifacts its reply claims to have written — the apply turn
writes the settlement verdict ostler reads, the resolver writes the operator's answer into
`context.md`. `apply-review.md` is reached from three states and is therefore one node id
with one handler, which is exactly the sharing the YAML had.
"""
from __future__ import annotations

import json
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from workhorse.artifacts import ArtifactWriter
from workhorse.pyflow import WorkflowFailed
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.review.flow import Review
from workhorse_workflows.coder.shared.review import resolve_review_context

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
CONTEXT_REL = f"{STORY_REL}/context.md"

#: What an escalating resolver leaves in `context.md` before handing the block to a person —
#: the shape `prompts/resolve-operator.md` mandates for the escalated arm.
ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "The retry is unsatisfiable either way; both readings cost something.\n"
    "Please pick which behaviour this story wants.\n"
)

#: The epic index ostler parses to learn the story exists — without it `prepare_story`'s
#: authored gate is skipped rather than satisfied, and every test below would pass for the
#: wrong reason.
EPIC_MD = """---
title: Epic One
status: active
---

# Epic One

## Stories

### STORY-1

- title: Story One
"""

#: An *authored* story. `settle_review` also rewrites the `**Status**:` line in here, which
#: is how the settlement's all-or-nothing status transition is observable.
STORY_MD = """---
type: story
---

# Story One

## Context

Users need a thing.

## Acceptance Criteria

- the thing exists

## Implementation Status

- **Status**: Not started
"""

#: The plan the dev flow left behind. `resolve_review_context` decodes it to learn which
#: code repos the reviewers may read — the multi-repo path, as opposed to the `repo=` one.
PLAN_CONTEXT: dict[str, Any] = {
    "story": STORY,
    "services": [
        {"repo": "api", "path": ".", "type": "go", "plan_file": "plan-api.md"},
        {"repo": "web", "path": ".", "type": "react-router", "plan_file": "plan-web.md"},
    ],
}


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo: one epic, one authored story, and the plan a dev run left behind.

    `plan.md` is written *untyped* on purpose — `stamp_specs` runs inside the review state
    and is what gives it its OKF type, so writing the frontmatter here would hide whether
    the stamping step ran at all.
    """
    write(repo / "docs" / "epics" / EPIC / "epic.md", EPIC_MD)
    write(repo / STORY_REL / "story.md", STORY_MD)
    write(repo / SPEC_REL / "plan-context.json", json.dumps(PLAN_CONTEXT, indent=2))
    write(repo / SPEC_REL / "plan.md", "# Plan\n\nDo the thing.\n")
    return repo


@pytest.fixture
def workspace(
    tmp_path: Path,
    docs: Path,
    git: Callable[..., subprocess.CompletedProcess],
    write: Callable[[Path, str], Path],
    ambient: dict[str, str],
) -> dict[str, Path]:
    """Two real git repos and the VSCode workspace file that names them.

    The reviewers are handed paths out of here, so the workspace has to be the real thing
    for `resolve_review_context`'s lookup to mean anything.
    """
    root = tmp_path / "ws"
    repos: dict[str, Path] = {}
    for name in ("api", "web"):
        path = root / name
        path.mkdir(parents=True)
        git(path, "init", "-q", "-b", "main")
        write(path / "README.md", f"# {name}\n")
        git(path, "add", "-A")
        git(path, "commit", "-qm", "Initial commit")
        repos[name] = path
    write(
        root / "acme.code-workspace",
        json.dumps({"folders": [{"name": n, "path": n} for n in repos]}),
    )
    ambient["workspace_file"] = str(root / "acme.code-workspace")
    return repos


# --------------------------------------------------------------------------- the agent


class _Agent:
    """A scripted stand-in for the flow's five prompts, writing what each claims to write.

    The knobs are the flow's branches: `needs_changes` makes the first N implementation
    reviews demand rework, `apply_status` is what every apply turn *claims* (which the
    settlement gate is free to overrule), `settle` makes the apply turn write a real
    `review-resolution.json` so that gate has something to verify, `evidence_after` is the
    apply pass from which it also writes the artifact that verdict cites, `escalate` makes
    the auto-operator hand the block to a human, and `explode` raises on a named prompt — a
    run killed mid-turn.
    """

    def __init__(
        self,
        docs: Path,
        *,
        needs_changes: int = 0,
        apply_status: str = "applied",
        settle: bool = False,
        evidence_after: int = 1,
        escalate: bool = False,
        explode: set[str] | None = None,
    ) -> None:
        self.docs = docs
        self.needs_changes = needs_changes
        self.apply_status = apply_status
        self.settle = settle
        self.evidence_after = evidence_after
        self.escalate = escalate
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []

    # -- the seam ---------------------------------------------------------

    def __call__(self, node: Any, ctx: Any, *args: Any, **kwargs: Any) -> Any:
        stem = Path(node.prompt).stem
        data = ctx.as_dict()
        self.calls.append(stem)
        self.args.append(data)
        if stem in self.explode:
            raise RuntimeError(f"killed during {stem}")
        handler = getattr(self, f"_{stem.replace('-', '_')}")
        return f"(scripted) {node.prompt}", handler(data, self.counts()[stem])

    def counts(self) -> Counter[str]:
        return Counter(self.calls)

    def args_for(self, stem: str) -> list[dict[str, Any]]:
        return [a for s, a in zip(self.calls, self.args, strict=True) if s == stem]

    # -- one handler per prompt -------------------------------------------

    def _code_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {
            "status": "ok",
            "findings": [{"severity": "minor", "note": "naming"}],
            "findings_summary": f"one minor finding (pass {nth})",
        }

    def _code_reuse(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        return {
            "status": "ok",
            "findings": [],
            "findings_summary": f"nothing duplicated (pass {nth})",
        }

    def _review_implementation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.needs_changes:
            return {"status": "needs_changes", "notes": "the handler ignores the timeout"}
        return {"status": "approved", "notes": "matches the acceptance criteria"}

    def _apply_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Claim a status, and — when asked — leave a real verdict for ostler to settle."""
        if self.settle:
            spec = self.docs / SPEC_REL
            if nth >= self.evidence_after:
                (spec / "evidence.md").write_text("# Evidence\n", encoding="utf-8")
            (spec / "review-resolution.json").write_text(
                json.dumps(
                    {
                        "status": "applied",
                        "findings": [
                            {
                                "id": "F1",
                                "disposition": "addressed",
                                "artifacts": ["evidence.md"],
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        return {"status": self.apply_status, "notes": f"apply pass {nth}"}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.escalate:
            self._escalate()
            return {"decision": "escalated", "summary": "needs a product call"}
        self._answer()
        return {"decision": "answered", "summary": "ship it without the retry"}

    # -- what the resolver leaves behind ----------------------------------

    def _answer(self) -> None:
        """Write the answer into the file `read_operator_context` reads it back out of."""
        (self.docs / CONTEXT_REL).write_text(
            "STATUS: ANSWERED\n\nDrop the retry; log it instead.\n", encoding="utf-8"
        )

    def _escalate(self) -> None:
        """An escalating resolver writes its note into the same file, it does not write nothing.

        `prompts/resolve-operator.md` mandates `STATUS: AWAITING_OPERATOR` plus what it tried
        and what the human must supply — the thing the escalated `Await` must not overwrite.
        """
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on.

    Patched over `poll_until_touched`, so it runs where the operator's edit would land: the
    questions are already in the file by then, which is what `seen` records.
    """

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        path.write_text(
            "STATUS: ANSWERED\n\nDrop the retry; log it instead.\n", encoding="utf-8"
        )

    return answered


def _output(run_env: RunEnv, node: Any) -> dict[str, Any]:
    """A node's recorded output — the artifact, not the return value the flow saw."""
    path = run_env.writer.run_dir / node.__name__ / "output.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- happy path


def test_an_approved_review_stamps_the_specs_and_stops(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The common case: two feeder reviews, one verdict, no feedback, done."""
    agent = _Agent(docs)
    run_env = env()

    result = drive_flow(Review(story=STORY), run_env, agent)

    assert result.status == "approved", result
    assert agent.counts() == {
        "code-review": 1,
        "code-reuse": 1,
        "review-implementation": 1,
    }, agent.counts()

    # The plan the dev run left untyped is an OKF Concept afterwards: `stamp_specs` ran
    # inside the review state, on the pass that could have rewritten it.
    assert (docs / SPEC_REL / "plan.md").read_text().startswith("---\n")

    # Both code repos were resolved off the plan context and granted to the reviewers.
    ctx = _output(run_env, resolve_review_context)
    assert sorted(Path(p).name for p in ctx["affected_repo_paths"]) == ["api", "web"]
    assert ctx["docs_repo_path"] == str(docs)


def test_the_implementation_reviewer_is_handed_both_feeder_verdicts(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The two verdicts travel as state parameters, and they arrive.

    Under the YAML engine `code_review_result` and `code_reuse_result` sat in the run context
    for the flow's lifetime. `self.output` reads only *node* outputs and an agent turn is not
    a node, so the port threads both models through five states — which means pydantic models
    are round-tripped through the checkpoint's `jsonable`/`TypeAdapter` pair on every
    transition. If that threading breaks, the reviewer silently renders two blanks and
    nothing else in the suite notices.
    """
    agent = _Agent(docs)

    drive_flow(Review(story=STORY), env(), agent)

    handed = agent.args_for("review-implementation")[0]
    assert handed["code_review_result"]["findings_summary"] == "one minor finding (pass 1)"
    assert handed["code_reuse_result"]["findings_summary"] == "nothing duplicated (pass 1)"


def test_the_reviewers_run_in_the_docs_repo_and_see_the_code_repos(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`cwd` is the docs repo for all three review turns, and the repos ride in `args`.

    The YAML gave the three review nodes a `cwd: docs_repo_path` and nothing else did; a cwd
    that differed between them would mean they were not reviewing the same thing.
    """
    agent = _Agent(docs)

    drive_flow(Review(story=STORY, branch="feat/x", pr_number="42"), env(), agent)

    first = agent.args_for("code-review")[0]
    assert sorted(Path(p).name for p in first["affected_repo_paths"]) == ["api", "web"]
    assert (first["branch"], first["pr_number"]) == ("feat/x", "42")


def test_an_explicit_repo_is_the_whole_affected_set(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    """The standalone-PR path: no plan context to decode, so the named repo is the set."""
    (docs / SPEC_REL / "plan-context.json").unlink()
    agent = _Agent(docs)
    run_env = env()

    drive_flow(Review(story=STORY, repo="api"), run_env, agent)

    paths = _output(run_env, resolve_review_context)["affected_repo_paths"]
    assert [Path(p).name for p in paths] == ["api"]


# --------------------------------------------------------------------------- review loop


def test_needs_changes_applies_once_and_exits_without_a_re_review(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`applied` leaves the loop on the settlement, not on a second reviewer pass.

    Deliberate, and the YAML's: re-running the reviewer here is what let it re-litigate
    settled findings and move the goalposts, so the deterministic settle *is* the re-verify.
    """
    agent = _Agent(docs, needs_changes=1)

    result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    assert agent.counts()["apply-review"] == 1, agent.counts()
    assert agent.counts()["review-implementation"] == 1, agent.counts()
    # The applier is handed the reviewer's brief, and nothing else.
    assert agent.args_for("apply-review")[0]["review_notes"] == (
        "the handler ignores the timeout"
    )


def test_the_apply_loop_is_bounded_and_then_reaches_the_operator(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Three apply passes that settle nothing escalate rather than looping forever.

    `MAX_REVIEW_REWORKS` is 3, so the third failed settlement is the one that gives up. The
    operator answers, the resolution is applied — a fourth turn on the same shared prompt —
    and the flow re-enters at `start` with a fresh budget and a fresh read of the code.
    """
    agent = _Agent(docs, needs_changes=1, apply_status="needs_changes")

    result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    assert agent.counts()["apply-review"] == 4, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_kind"] == "review"
    # Re-entering at `start` re-runs both feeder reviews: the answer is binding, not asserted.
    assert agent.counts()["code-review"] == 2, agent.counts()
    assert agent.counts()["code-reuse"] == 2, agent.counts()
    assert agent.counts()["review-implementation"] == 2, agent.counts()


def test_a_blocked_settlement_escalates_without_spending_the_budget(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` is a finding nobody can settle, so re-applying it is not the answer."""
    agent = _Agent(docs, needs_changes=1, apply_status="blocked")

    result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    # One apply, straight to the operator, then the resolution apply.
    assert agent.counts()["apply-review"] == 2, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()


def test_repeated_operator_cycles_fail_after_the_outer_bound(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Local rework resets cannot buy unbounded review/operator cycles."""
    agent = _Agent(docs, needs_changes=99, apply_status="blocked")

    with pytest.raises(WorkflowFailed, match="still blocked after 3 operator resolution"):
        drive_flow(Review(story=STORY), env(), agent)

    assert agent.counts()["resolve-operator"] == Review.MAX_REVIEW_BLOCKS, agent.counts()
    assert agent.counts()["code-review"] == Review.MAX_REVIEW_BLOCKS + 1, agent.counts()


# --------------------------------------------------------------------- the settlement gate


def test_the_settlement_gate_overrules_an_unproven_applied_claim(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The anti-gaming gate, driven through the real `ostler edit settle-review`.

    Both apply turns *claim* `applied`. The first cites an artifact that is not on disk, so
    ostler's per-finding verification leaves the finding open and the gate downgrades the
    claim to `needs_changes`; the second writes the artifact and the same claim is allowed
    through. The flow's branch therefore never reads the turn's own status — which is the
    whole point of the node overwriting `impl_result` in the YAML.
    """
    agent = _Agent(docs, needs_changes=1, apply_status="applied", settle=True,
                   evidence_after=2)

    result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    assert agent.counts()["apply-review"] == 2, agent.counts()

    # ostler wrote the per-finding ledger, and the story status followed it.
    ledger = json.loads((docs / SPEC_REL / "review-settlement.json").read_text())
    assert ledger["all_verified"] is True, ledger
    assert ledger["verified"] == ["F1"], ledger
    assert "Review fixes applied" in (docs / STORY_REL / "story.md").read_text()


def test_a_story_with_no_verdict_sidecar_passes_the_claim_through(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """No `review-resolution.json` at all means the prior behavior, not an over-block.

    A repo whose apply prompt does not emit a verdict keeps working; the gate binds only
    where there is something to verify.
    """
    agent = _Agent(docs, needs_changes=1, apply_status="applied")

    result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    assert not (docs / SPEC_REL / "review-settlement.json").exists()


# --------------------------------------------------------------------------- the operator


@pytest.mark.parametrize("operator_mode", ["human", "operator"])
def test_human_operator_modes_wait_on_the_story_context_file(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    operator_mode: str,
) -> None:
    """Canonical `human` and legacy `operator` skip the resolver and block on the file.

    The questions are the reviewer's notes, written next to the story — where
    `await_operator.py` put them and where the operator is reading the story they are about.
    """
    seen: list[str] = []
    agent = _Agent(docs, needs_changes=1, apply_status="blocked")

    with patch.object(pyflow_driver, "poll_until_touched", _answers(seen)):
        result = drive_flow(Review(story=STORY, operator_mode=operator_mode), env(), agent)

    assert result.status == "approved", result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == 1 and "the handler ignores the timeout" in seen[0], seen


def test_an_escalating_resolver_falls_through_to_the_human(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The human path is the resolver's fallback, not a separate mode.

    This is the arm the port's operator-gate split exists for: the YAML fell into
    `await_operator_review` unconditionally and let the file's `STATUS:` line decide whether
    that halted, so only the escalated arm may wait here.
    """
    seen: list[str] = []
    agent = _Agent(docs, needs_changes=1, apply_status="blocked", escalate=True)

    with patch.object(pyflow_driver, "poll_until_touched", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The resolver's note, not the block summary: the escalated `Await` waits on this file
    # without rewriting it, so the human arrives to what the resolver already tried. See
    # `dev`'s `test_an_escalating_resolver_leaves_its_note_for_the_human`.
    assert seen == [ESCALATION_NOTE], seen


def test_an_answered_resolution_never_waits(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The other half of the split: a resolver that answered must not halt the run.

    `poll_until_touched` is replaced with something that fails the test if it is reached, so
    an accidental unconditional `Await` cannot pass by having a helpful stub answer it.
    """

    def never(path: Path, **kwargs: Any) -> None:
        raise AssertionError(f"an answered resolution waited on {path}")

    agent = _Agent(docs, needs_changes=1, apply_status="blocked")

    with patch.object(pyflow_driver, "poll_until_touched", never):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    # The answer reached the applier as operator feedback, not as review notes.
    resolved = agent.args_for("apply-review")[-1]
    assert "Drop the retry" in resolved["operator_feedback"]


# --------------------------------------------------------------------------- feedback


def test_dropped_feedback_buys_exactly_one_rework_pass(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    """A note in the inbox reworks once and re-reviews; reading it is what consumes it.

    The counter is carried rather than reset — the YAML's wiring — so the feedback pass
    re-enters the review loop with whatever allowance is left rather than a fresh one.
    """
    write(docs / SPEC_REL / "feedback.md", "STATUS: NEW\n\nRename the endpoint.\n")
    agent = _Agent(docs)

    result = drive_flow(Review(story=STORY), env(), agent)

    assert result.status == "approved", result
    assert agent.counts()["review-implementation"] == 2, agent.counts()
    assert agent.counts()["apply-review"] == 1, agent.counts()
    # The feedback *is* the work: no stale findings go in alongside it.
    pass_ = agent.args_for("apply-review")[0]
    assert pass_["review_notes"] == ""
    assert "Rename the endpoint" in pass_["operator_feedback"]
    # And the inbox is stamped, so the second poll finds nothing new.
    assert "STATUS: CONSUMED" in (docs / SPEC_REL / "feedback.md").read_text()


# --------------------------------------------------------------------------- resume


def test_a_run_killed_mid_review_resumes_on_the_review_state(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so both verdicts survive the kill.

    This is the resume shape the port has to match, and it is the strongest evidence that a
    pydantic model is a legal state parameter: the two feeder verdicts go into the checkpoint
    as JSON and come back out as models, and the resumed run re-enters on `review` without
    re-running either feeder turn.
    """
    run_env = env()
    run_dir = run_env.writer.run_dir

    with pytest.raises(RuntimeError, match="killed during review-implementation"):
        drive_flow(
            Review(story=STORY), run_env, _Agent(docs, explode={"review-implementation"})
        )

    checkpoint = parse_checkpoint((run_dir / ArtifactWriter.CHECKPOINT_FILE).read_text())
    resume = read_resume(checkpoint)
    assert resume.state == "review", resume
    assert resume.flow == "Review", resume
    # Only what the transition actually bound is checkpointed; `review_rework` keeps its
    # default on the way back in, which is the same 0 the killed run was carrying.
    assert sorted(resume.params) == ["code_reuse", "code_review", "review_blocks"], resume.params
    assert resume.params.pop("review_blocks") == 0
    assert resume.params["code_review"]["findings_summary"] == "one minor finding (pass 1)"

    agent = _Agent(docs)
    result = drive_flow(Review(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert result.status == "approved", result
    assert agent.counts() == {"review-implementation": 1}, agent.counts()
