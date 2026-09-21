"""End-to-end tests for the `review` flow — the settlement gate, the loop, the operator."""
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

ESCALATION_NOTE = (
    "STATUS: AWAITING_OPERATOR\n\n"
    "The retry is unsatisfiable either way; both readings cost something.\n"
    "Please pick which behaviour this story wants.\n"
)

RESOLVER_TRIED = (
    "implemented the bounded retry — the reviewer's second finding then contradicts it",
    "read the epic for a stated retry policy — it states none",
)

EPIC_MD = """---
title: Epic One
status: active
---

# Epic One

## Stories

### STORY-1

- title: Story One
"""

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

## Non-Functional Acceptance Criteria

- the thing is fast

## Technical Notes

- the thing is a function

## Implementation Status

- **Status**: Not started
"""

PLAN_CONTEXT: dict[str, Any] = {
    "story": STORY,
    "services": [
        {"repo": "api", "path": ".", "type": "go", "plan_file": "plan-api.md"},
        {"repo": "web", "path": ".", "type": "react-router", "plan_file": "plan-web.md"},
    ],
}




@pytest.fixture
def docs(repo: Path, write: Callable[[Path, str], Path]) -> Path:
    """The docs repo: one epic, one authored story, and the plan a dev run left behind."""
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
    """Two real git repos and the VSCode workspace file that names them."""
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




class _Agent:
    """A scripted stand-in for the flow's five prompts, writing what each claims to write."""

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
        self.resolver_answers = resolver_answers
        self.explode = explode or set()
        self.calls: list[str] = []
        self.args: list[dict[str, Any]] = []


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
            return {"status": "applied", "notes": f"applied what the operator said (pass {nth})"}
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


    def _escalate(self) -> None:
        """An escalating resolver writes its note into the same file, it does not write nothing."""
        (self.docs / CONTEXT_REL).write_text(ESCALATION_NOTE, encoding="utf-8")


def _answers(seen: list[str]) -> Callable[..., None]:
    """A stand-in for the human an `Await` is waiting on."""

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

    assert (docs / SPEC_REL / "plan.md").read_text().startswith("---\n")

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
    """The review verdict travels as a state parameter, and it arrives split on confidence."""
    agent = _Agent(docs)

    drive_flow(Review(story=STORY), env(), agent)

    handed = agent.args_for("review-implementation")[0]
    must_fix = handed["must_fix_findings"]
    advisory = handed["advisory_findings"]
    assert "api-service/link.go:12" in must_fix
    assert "Category: Reuse (confidence 82)" in must_fix
    assert "Required fix: call the shared path helper" in must_fix
    assert "api-service/link.go:40" not in must_fix
    assert "api-service/link.go:40" in advisory


def test_the_reviewers_run_in_the_docs_repo_and_see_the_code_repos(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`cwd` is the docs repo for all three review turns, and the repos ride in `args`."""
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




def test_needs_changes_applies_once_and_exits_without_a_re_review(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`applied` leaves the loop on the settlement, not on a second reviewer pass."""
    agent = _Agent(docs, needs_changes=1, settle=True)

    result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["apply-review"] == 1, agent.counts()
    assert agent.counts()["review-implementation"] == 1, agent.counts()
    assert agent.args_for("apply-review")[0]["review_notes"] == (
        "the handler ignores the timeout"
    )


def test_the_apply_loop_is_bounded_and_then_reaches_the_operator(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Three apply passes that settle nothing escalate rather than looping forever."""
    agent = _Agent(docs, needs_changes=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["apply-review"] == 4, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.args_for("resolve-operator")[0]["block_kind"] == "review"
    assert agent.counts()["code-review"] == 2, agent.counts()
    assert agent.counts()["review-implementation"] == 2, agent.counts()


def test_a_blocked_settlement_escalates_without_spending_the_budget(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` is a finding nobody can settle, so re-applying it is not the answer."""
    agent = _Agent(docs, needs_changes=1, settle=True, settle_blocked=True)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["apply-review"] == 2, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    resolved = agent.args_for("apply-review")[-1]
    assert "Drop the retry" in resolved["operator_feedback"]


def test_a_reviewer_that_cannot_reach_a_verdict_escalates_instead_of_reworking(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A blocked verdict is not a demand for changes, and the applier is not its audience."""
    agent = _Agent(docs, review_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.counts()["apply-review"] == 1, agent.counts()
    (gate,) = seen
    assert "the story's acceptance criteria contradict" in gate, gate


def test_a_code_review_that_could_not_read_the_diff_escalates(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """`blocked` from the code review is not "nothing to report" — it is no review at all."""
    agent = _Agent(docs, code_review_blocked=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    assert agent.counts()["code-review"] == 2, agent.counts()
    assert agent.counts()["review-implementation"] == 1, agent.counts()
    (gate,) = seen
    assert "mid-rebase" in gate, gate


def test_a_resolver_that_grounds_its_answer_settles_a_review_block(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """A review block is the one most often already answered by an installed skill."""
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
    """Local rework resets do not buy unbounded *resolver* turns — but the run never dies."""
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




def test_the_settlement_gate_overrules_an_unproven_applied_claim(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The anti-gaming gate, driven through the real `ostler edit settle-review`."""
    agent = _Agent(docs, needs_changes=1, settle=True, evidence_after=2)

    result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["apply-review"] == 2, agent.counts()

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
    """No `review-resolution.json` at all is a turn that did not finish its contract."""
    agent = _Agent(docs, needs_changes=1)
    seen: list[str] = []

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert not (docs / SPEC_REL / "review-settlement.json").exists()
    assert agent.counts()["apply-review"] == Review.MAX_REVIEW_REWORKS + 1, agent.counts()
    assert agent.counts()["resolve-operator"] == 1, agent.counts()


def test_a_previous_cycles_settlement_cannot_settle_this_ones_findings(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """Findings are numbered positionally and the numbers restart every review round."""
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
    assert not (spec / "review-resolution.json").exists()
    assert not (spec / "review-settlement.json").exists()




@pytest.mark.parametrize("operator_mode", ["human", "operator"])
def test_human_operator_modes_wait_on_the_story_context_file(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    operator_mode: str,
) -> None:
    """Canonical `human` and legacy `operator` skip the resolver and block on the file."""
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
    """`resolve_review` investigates and always parks — it never decides on the operator's behalf, exactly as `dev` settled it."""
    seen: list[str] = []
    agent = _Agent(docs, needs_changes=1)

    with patch.object(pyflow_driver, "wait_for_answer", _answers(seen)):
        result = drive_flow(Review(story=STORY), env(), agent)

    assert isinstance(result, ReviewResult), result
    assert agent.counts()["resolve-operator"] == 1, agent.counts()
    (gate,) = seen
    assert "**Escalation #1 " in gate, gate
    assert all(line in gate for line in RESOLVER_TRIED), gate
    assert ESCALATION_NOTE.strip() in gate, gate




def test_dropped_feedback_buys_exactly_one_rework_pass(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
    write: Callable[[Path, str], Path],
) -> None:
    """A note in the inbox reworks once and re-reviews; reading it is what consumes it."""
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
    pass_ = agent.args_for("apply-review")[0]
    assert pass_["review_notes"] == ""
    assert "Rename the endpoint" in pass_["operator_feedback"]
    messages = inbox.all_messages(run_env.writer.run_dir / INBOX_FILE)
    assert len(messages) == 1, messages
    assert messages[0].reply, messages




def test_a_run_killed_mid_review_resumes_on_the_review_state(
    docs: Path,
    workspace: dict[str, Path],
    env: Callable[..., RunEnv],
    drive_flow: Callable[..., Any],
) -> None:
    """The checkpoint is written before a state runs, so both verdicts survive the kill."""
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
    assert sorted(resume.params) == ["code_review", "loop"], resume.params
    assert resume.params["loop"] == {"rework": 0, "blocks": 0, "session_turns": 0}
    assert resume.params["code_review"]["findings_summary"] == "one minor finding (pass 1)"

    agent = _Agent(docs)
    result = drive_flow(Review(**resume.inputs), env(run_dir=run_dir), agent, resume)

    assert isinstance(result, ReviewResult), result
    assert agent.counts() == {"review-implementation": 1}, agent.counts()
