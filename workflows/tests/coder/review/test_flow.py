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
from workhorse import inbox
from workhorse.artifacts import ArtifactWriter
from workhorse.cli.inbox import INBOX_FILE
from workhorse.pyflow import driver as pyflow_driver
from workhorse.pyflow.driver import read_resume
from workhorse.pyflow.engine import RunEnv
from workhorse.records import parse_checkpoint

from workhorse_workflows.coder.review.flow import (
    MUST_FIX_CONFIDENCE,
    Review,
    findings_block,
    split_on_confidence,
)
from workhorse_workflows.coder.shared.review import resolve_review_context
from workhorse_workflows.coder.shared.schemas.review import ReviewFinding, ReviewResult

STORY = "STORY-1"
EPIC = "EPIC-1"
SPEC_REL = f"docs/specs/{STORY}"
STORY_REL = f"docs/epics/{EPIC}/stories/{STORY}"
CONTEXT_REL = f"{STORY_REL}/context.md"

#: What an escalating resolver leaves in `context.md` before handing the block to a person —
#: the shape `review/prompts/resolve-operator.md` mandates for the escalated arm.
ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "The retry is unsatisfiable either way; both readings cost something.\n"
    "Please pick which behaviour this story wants.\n"
)

#: What that resolver reports it ruled out, which the composed gate publishes verbatim.
RESOLVER_TRIED = (
    "implemented the bounded retry — the reviewer's second finding then contradicts it",
    "read the epic for a stated retry policy — it states none",
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

## Dependencies

(none)

## Fixtures

(none)

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
    reviews demand rework, `settle` makes the apply turn write a real
    `review-resolution.json` so the settlement gate has something to verify,
    `settle_blocked` makes that verdict report the finding unresolvable, `evidence_after` is
    the apply pass from which it also writes the artifact the verdict cites, `review_blocked`
    makes the first N implementation reviews report they could not reach a verdict,
    `code_review_blocked` does the same for the first N code-review passes, and
    `explode` raises on a named prompt — a run killed mid-turn. There is no "answer directly" knob:
    the resolver always escalates to a human, per `resolve_review`'s contract — see the
    module docstring.
    """

    def __init__(
        self,
        docs: Path,
        *,
        needs_changes: int = 0,
        review_blocked: int = 0,
        code_review_blocked: int = 0,
        settle: bool = False,
        settle_blocked: bool = False,
        evidence_after: int = 1,
        explode: set[str] | None = None,
        resolver_answers: bool = False,
    ) -> None:
        self.docs = docs
        self.needs_changes = needs_changes
        self.review_blocked = review_blocked
        self.code_review_blocked = code_review_blocked
        self.settle = settle
        self.settle_blocked = settle_blocked
        self.evidence_after = evidence_after
        #: Whether the resolver settles the block itself rather than parking on it — the
        #: `answered` arm, which writes the operator's answer where a human would have.
        self.resolver_answers = resolver_answers
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
        if nth <= self.code_review_blocked:
            return {
                "status": "blocked",
                "findings": [],
                "findings_summary": "api-service is mid-rebase — the diff is a conflict",
            }
        return {
            "status": "findings",
            "findings": [
                {
                    "target": "api-service/link.go:12",
                    "issue": "the handler name reads as a noun",
                    "repair": "rename it to CreateLink",
                    "category": "Bug",
                    "score": 88,
                },
                {
                    "target": "api-service/path.go:4",
                    "issue": "re-derives the canonical path",
                    "repair": "call the shared path helper",
                    "category": "Reuse",
                    "score": 82,
                },
                {
                    "target": "api-service/link.go:40",
                    "issue": "the receiver name is one letter",
                    "repair": "spell it out",
                    "category": "Standard",
                    "score": 40,
                },
            ],
            "findings_summary": f"one minor finding (pass {nth})",
        }

    def _review_implementation(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if nth <= self.review_blocked:
            return {"status": "blocked", "notes": "the story's acceptance criteria contradict"}
        if nth <= self.needs_changes:
            return {"status": "needs_changes", "notes": "the handler ignores the timeout"}
        return {"status": "approved", "notes": "matches the acceptance criteria"}

    def _apply_review(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        """Leave a verdict for ostler to settle — the only thing the loop reads back."""
        if self.settle:
            spec = self.docs / SPEC_REL
            if nth >= self.evidence_after:
                (spec / "evidence.md").write_text("# Evidence\n", encoding="utf-8")
            (spec / "review-resolution.json").write_text(
                json.dumps(
                    {
                        "status": "blocked" if self.settle_blocked else "applied",
                        "findings": [
                            {
                                "id": "F1",
                                "disposition": (
                                    "blocked" if self.settle_blocked else "addressed"
                                ),
                                "artifacts": ["evidence.md"],
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        if data.get("operator_feedback"):
            # The two sites handed an answer from outside — the operator resolution and the
            # feedback note. Those two do read the turn's own status, and a turn that has
            # just been told what to do is not still blocked on being told: a fake that says
            # it is asks the operator the same question forever.
            return {"status": "applied", "notes": f"applied what the operator said (pass {nth})"}
        # The rework loop discards this: `verify_review_resolution` is what it believes.
        return {"status": "applied", "notes": f"apply pass {nth}"}

    def _resolve_operator(self, data: dict[str, Any], nth: int) -> dict[str, Any]:
        if self.resolver_answers:
            (self.docs / CONTEXT_REL).write_text(
                "STATUS: ANSWERED\n\nDrop the retry; log it instead.\n", encoding="utf-8"
            )
            return {
                "decision": "answered",
                "summary": "the retry policy is settled by the installed go-service skill",
                "grounded": [".claude/skills/go-service/SKILL.md:31 — 'never retry a write'"],
                "record": "do-writes-retry",
            }
        self._escalate()
        return {
            "decision": "escalated",
            "summary": "needs a product call",
            "tried": list(RESOLVER_TRIED),
        }

    # -- what the resolver leaves behind ----------------------------------

    def _escalate(self) -> None:
        """An escalating resolver writes its note into the same file, it does not write nothing.

        `review/prompts/resolve-operator.md` mandates `STATUS: AWAITING_OPERATOR` plus what it tried
        and what the human must supply — the thing the escalated `Await` must not overwrite.
        """
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on.

    Patched over `wait_for_answer`, so it runs where the operator's edit would land: the
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

    assert isinstance(result, ReviewResult), result
    assert agent.counts() == {
        "code-review": 1,
        "review-implementation": 1,
    }, agent.counts()

    # The plan the dev run left untyped is an OKF Concept afterwards: `stamp_specs` ran
    # inside the review state, on the pass that could have rewritten it.
    assert (docs / SPEC_REL / "plan.md").read_text().startswith("---\n")

    # Both code repos were resolved off the plan context and granted to the reviewers.
    ctx = _output(run_env, resolve_review_context)
    assert sorted(Path(p).name for p in ctx["affected_repo_paths"]) == ["api", "web"]
    assert ctx["docs_repo_path"] == str(docs)



def test_a_findings_block_says_none_rather_than_rendering_empty() -> None:
    """An empty list is still a section, so the prompt carries no `{% if %}` arm for it."""
    assert findings_block([]) == "None."


def test_the_split_is_inclusive_at_the_confidence_line() -> None:
    """A finding scored exactly at the line binds — the reviewer's `>= 80` is must-fix."""
    at = ReviewFinding(target="a.go:1", issue="i", repair="r", category="Bug",
                       score=MUST_FIX_CONFIDENCE)
    below = ReviewFinding(target="b.go:1", issue="i", repair="r", category="Bug",
                          score=MUST_FIX_CONFIDENCE - 1)

    must_fix, advisory = split_on_confidence([at, below])

    assert must_fix == [at]
    assert advisory == [below]


def test_the_implementation_reviewer_is_handed_both_feeder_verdicts(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The review verdict travels as a state parameter, and it arrives split on confidence.

    Under the YAML engine `code_review_result` sat in the run context for the flow's
    lifetime. `self.output` reads only *node* outputs and an agent turn is not a node, so
    the port threads the model through five states — which means pydantic models are
    round-tripped through the checkpoint's `jsonable`/`TypeAdapter` pair on every
    transition. If that threading breaks, the reviewer silently renders a blank and
    nothing else in the suite notices.

    What the reviewer is handed is two rendered lists rather than the model: the prompt
    used to be told to drop everything scoring below 80, which is a filter nothing
    downstream could check. `MUST_FIX_CONFIDENCE` splits them here instead.
    """
    agent = _Agent(docs)

    drive_flow(Review(story=STORY), env(), agent)

    handed = agent.args_for("review-implementation")[0]
    must_fix = handed["must_fix_findings"]
    advisory = handed["advisory_findings"]
    assert "api-service/link.go:12" in must_fix
    # The reuse hunt is a lens of that one pass now, so its findings ride in the same list.
    assert "Category: Reuse (confidence 82)" in must_fix
    # And each finding keeps the half that lets a fixer act on it rather than an operator.
    assert "Required fix: call the shared path helper" in must_fix
    # The one scored below the line is demoted, not deleted.
    assert "api-service/link.go:40" not in must_fix
    assert "api-service/link.go:40" in advisory


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
    agent = _Agent(docs, needs_changes=1, settle=True)

    result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
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

    `MAX_REVIEW_REWORKS` is 3, so the third failed settlement is the one that blocks. The
    resolver escalates, the human answers, the resolution is applied — a fourth turn on the
    same shared prompt — and the flow re-enters at `start` with a fresh budget and a fresh
    read of the code.
    """
    agent = _Agent(docs, needs_changes=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["apply-review"] == 4, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_kind"] == "review"
    # Re-entering at `start` re-runs the feeder review: the answer is binding, not asserted.
    assert agent.counts()["code-review"] == 2, agent.counts()
    assert agent.counts()["review-implementation"] == 2, agent.counts()


def test_a_blocked_settlement_escalates_without_spending_the_budget(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` is a finding nobody can settle, so re-applying it is not the answer.

    The verdict reports the finding unresolvable and ostler's ledger says so; the block is
    the ledger's, not the turn's own claim about itself.
    """
    agent = _Agent(docs, needs_changes=1, settle=True, settle_blocked=True)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    # One apply, straight to the operator, then the resolution apply.
    assert agent.counts()["apply-review"] == 2, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The human's answer reached the applier as operator feedback, not as review notes.
    resolved = agent.args_for("apply-review")[-1]
    assert "Drop the retry" in resolved["operator_feedback"]


def test_a_reviewer_that_cannot_reach_a_verdict_escalates_instead_of_reworking(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blocked verdict is not a demand for changes, and the applier is not its audience.

    Both non-approving arms used to land on the rework guard, so a reviewer reporting it
    could not review at all bought three apply passes against notes describing why no
    review was possible — three turns to arrive back here with the same sentence.
    """
    agent = _Agent(docs, review_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # Only the apply that carries the operator's answer — the rework budget went unspent.
    assert agent.counts()["apply-review"] == 1, agent.counts()
    (gate,) = seen
    assert "the story's acceptance criteria contradict" in gate, gate


def test_a_code_review_that_could_not_read_the_diff_escalates(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` from the code review is not "nothing to report" — it is no review at all.

    It used to log a warning and run the binding reviewer anyway, which produced a verdict
    over a diff nobody had read and left that fact nowhere but the log. It goes to the
    operator, whose answer re-enters at `start` and buys a fresh code-review pass.
    """
    agent = _Agent(docs, code_review_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The blocked pass, then the one the operator's answer bought.
    assert agent.counts()["code-review"] == 2, agent.counts()
    # The implementation reviewer only ever saw the diff the second pass could read.
    assert agent.counts()["review-implementation"] == 1, agent.counts()
    (gate,) = seen
    assert "mid-rebase" in gate, gate


def test_a_resolver_that_grounds_its_answer_settles_a_review_block(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A review block is the one most often already answered by an installed skill.

    "Should this retry?" is a convention the repo has written down, not a product call, so
    the resolver quotes the skill and applies it. Nothing parks — patching `wait_for_answer`
    to fail is what proves the flow never reached a human.
    """
    agent = _Agent(docs, review_blocked=1, resolver_answers=True)

    def never(path: Path, **kwargs: Any) -> None:
        raise AssertionError(f"a grounded answer must not park on {path}")

    with patch.object(pyflow_driver, "wait_for_answer", never):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert "STATUS: CONSUMED" in (docs / CONTEXT_REL).read_text()


def test_repeated_operator_cycles_never_give_up(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Local rework resets do not buy unbounded *resolver* turns — but the run never dies.

    Once `MAX_REVIEW_BLOCKS` resolver turns are spent, every further block goes straight to
    a human instead — the same "no dead end" contract `dev` settled. The story only finishes
    once the human's answer actually fixes it, not because the flow gave up asking.
    """
    agent = _Agent(docs, needs_changes=99)
    seen: list[str] = []

    def answered(path: Path, **kwargs: Any) -> None:
        seen.append(path.read_text(encoding="utf-8"))
        if len(seen) >= Review.MAX_REVIEW_BLOCKS + 2:
            agent.needs_changes = 0
        path.write_text(
            "STATUS: ANSWERED\n\nDrop the retry; log it instead.\n", encoding="utf-8"
        )

    with patch.object(pyflow_driver, "wait_for_answer", answered):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == Review.MAX_REVIEW_BLOCKS, agent.counts()
    assert len(seen) == Review.MAX_REVIEW_BLOCKS + 2, seen


# --------------------------------------------------------------------- the settlement gate


def test_the_settlement_gate_overrules_an_unproven_applied_claim(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The anti-gaming gate, driven through the real `ostler edit settle-review`.

    Both apply turns write a verdict claiming `applied`. The first cites an artifact that is
    not on disk, so ostler's per-finding verification leaves the finding open and the gate
    answers `needs_changes`; the second writes the artifact and the same verdict is allowed
    through. The flow's branch never reads the turn's own reply at all — which is the whole
    point of the node overwriting `impl_result` in the YAML.
    """
    agent = _Agent(docs, needs_changes=1, settle=True, evidence_after=2)

    result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["apply-review"] == 2, agent.counts()

    # ostler wrote the per-finding ledger, and the story status followed it.
    ledger = json.loads((docs / SPEC_REL / "review-settlement.json").read_text())
    assert ledger["all_verified"] is True, ledger
    assert ledger["verified"] == ["F1"], ledger
    assert "Review fixes applied" in (docs / STORY_REL / "story.md").read_text()


def test_a_story_with_no_verdict_sidecar_is_re_applied_not_believed(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """No `review-resolution.json` at all is a turn that did not finish its contract.

    It used to pass the turn's own claim through, which made the one thing this gate exists
    to stop — an `applied` nobody verified — reachable by writing no verdict at all. The
    rework budget is spent re-applying instead, and the block that follows is the operator's.
    """
    agent = _Agent(docs, needs_changes=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert not (docs / SPEC_REL / "review-settlement.json").exists()
    # The whole rework budget, then the operator — never a settlement nobody verified.
    assert agent.counts()["apply-review"] == Review.MAX_REVIEW_REWORKS + 1, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()


def test_a_previous_cycles_settlement_cannot_settle_this_ones_findings(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Findings are numbered positionally and the numbers restart every review round.

    So a resolution left behind by an earlier round names the same ids as the review that
    just replaced it, and `settle-review` would verify the old round's artifacts against the
    new round's findings and call every one of them settled — a fresh set of required fixes
    reaching QA having never been applied. The round clears both sidecars before it writes
    the findings they will be checked against.
    """
    spec = docs / SPEC_REL
    (spec / "review-resolution.json").write_text(
        json.dumps({"findings": [{"id": "F1", "disposition": "addressed"}]}), encoding="utf-8"
    )
    (spec / "review-settlement.json").write_text(
        json.dumps({"all_verified": True, "any_blocked": False, "verified": ["F1"]}),
        encoding="utf-8",
    )

    agent = _Agent(docs, needs_changes=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    # Neither stale sidecar survived into the round, so nothing settled on last round's proof.
    assert not (spec / "review-resolution.json").exists()
    assert not (spec / "review-settlement.json").exists()


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
    agent = _Agent(docs, needs_changes=1)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY, operator_mode=operator_mode), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 0, agent.counts()
    assert len(seen) == 1 and "the handler ignores the timeout" in seen[0], seen


def test_the_resolver_always_escalates_to_the_human(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`resolve_review` investigates and always parks — it never decides on the operator's
    behalf, exactly as `dev` settled it. See the module docstring.
    """
    seen: list[str] = []
    agent = _Agent(docs, needs_changes=1)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    # The composed gate, not the block summary alone: the human arrives to the escalation
    # number, what the resolver ruled out, and the resolver's own note carried forward.
    (gate,) = seen
    assert "**Escalation #1 " in gate, gate
    assert all(line in gate for line in RESOLVER_TRIED), gate
    assert ESCALATION_NOTE.strip() in gate, gate


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
    run_env = env()
    inbox.append(
        run_env.writer.run_dir / INBOX_FILE,
        id="note-1",
        body="Rename the endpoint.",
        at="2024-01-01T00:00:00+00:00",
    )
    agent = _Agent(docs)

    result = drive_flow(Review(story=STORY), run_env, agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["review-implementation"] == 2, agent.counts()
    assert agent.counts()["apply-review"] == 1, agent.counts()
    # The feedback *is* the work: no stale findings go in alongside it.
    pass_ = agent.args_for("apply-review")[0]
    assert pass_["review_notes"] == ""
    assert "Rename the endpoint" in pass_["operator_feedback"]
    # And the message is replied to, so the second poll finds nothing new.
    messages = inbox.all_messages(run_env.writer.run_dir / INBOX_FILE)
    assert len(messages) == 1, messages
    assert messages[0].reply, messages


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
    # Both of the state's parameters are checkpointed, counters included: the lap is one
    # object, so a resume cannot pick up some of the budget and default the rest.
    assert sorted(resume.params) == ["code_review", "loop"], resume.params
    assert resume.params["loop"] == {"rework": 0, "blocks": 0, "session_turns": 0}
    assert resume.params["code_review"]["findings_summary"] == "one minor finding (pass 1)"

    agent = _Agent(docs)
    result = drive_flow(Review(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert isinstance(result, ReviewResult), result
    assert agent.counts() == {"review-implementation": 1}, agent.counts()
