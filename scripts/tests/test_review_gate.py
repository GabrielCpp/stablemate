"""When the review gate reviews, which model rules, and what it hands the agent."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import review_gate
from conftest import git, strict_repo
from review_gate import Block, GiveUp, StopEvent
from review_state import BASE_STATE_FILE, EMPTY_STATE, HOOK_STATE_FILE, load_state
from review_verdict import Finding, ReviewError, Verdict


@dataclass
class FakeReviewer:
    problems_per_call: list[list[str]]
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, prompt: str, model: str) -> Verdict:
        self.calls.append((prompt, model))
        if not self.problems_per_call:
            raise ReviewError("the reviewer ran out of quota")
        problems = self.problems_per_call.pop(0)
        findings = tuple(
            Finding(file="pkg/strict/core.py", line=1, rule="bad-name", problem=problem)
            for problem in problems
        )
        return Verdict(model=model, findings=findings)


def broken_reviewer(prompt: str, model: str) -> Verdict:
    raise ReviewError("quota exhausted")


def _stop(repo: Path) -> StopEvent:
    return StopEvent(cwd=repo)


def _edit_strict(repo: Path, body: str = "VALUE = 3\n") -> None:
    (repo / "pkg" / "strict" / "core.py").write_text(body, encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def test_a_change_outside_the_scope_is_not_reviewed(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "loose" / "other.py").write_text("VALUE = 9\n", encoding="utf-8")
    reviewer = FakeReviewer([])
    assert review_gate.hook_decision(repo, _stop(repo), reviewer) is None
    assert reviewer.calls == []


def test_a_session_in_another_directory_is_not_reviewed(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path / "repo")
    _edit_strict(repo)
    reviewer = FakeReviewer([])
    assert review_gate.hook_decision(repo, StopEvent(cwd=tmp_path), reviewer) is None
    assert reviewer.calls == []


def test_the_stop_payload_names_the_session_directory(tmp_path: Path) -> None:
    text = json.dumps({"hook_event_name": "Stop", "cwd": str(tmp_path), "stop_hook_active": False})
    assert review_gate.parse_stop_event(text) == StopEvent(cwd=tmp_path)


@pytest.mark.parametrize("text", ["", "not json", "[]", json.dumps({"cwd": 3})])
def test_a_payload_without_a_directory_is_no_stop_event(text: str) -> None:
    assert review_gate.parse_stop_event(text) is None


def test_the_reviewer_reads_the_rubric_and_the_diff(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    reviewer = FakeReviewer([[]])
    assert review_gate.hook_decision(repo, _stop(repo), reviewer) is None
    prompt, model = reviewer.calls[0]
    assert model == review_gate.PRIMARY_MODEL
    assert "string-keyed-state" in prompt
    assert "+VALUE = 3" in prompt


def test_an_untracked_file_in_the_scope_is_reviewed(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "strict" / "fresh.py").write_text("FRESH = 1\n", encoding="utf-8")
    reviewer = FakeReviewer([[]])
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert "+FRESH = 1" in reviewer.calls[0][0]


def test_an_approved_tree_is_not_reviewed_twice(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    reviewer = FakeReviewer([[]])
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    _commit(repo, "approved")
    assert review_gate.hook_decision(repo, _stop(repo), reviewer) is None
    assert len(reviewer.calls) == 1


def test_commits_made_after_an_approval_are_not_reviewed_again(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    reviewer = FakeReviewer([[], []])
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    _commit(repo, "approved")
    _edit_strict(repo, "VALUE = 4\n")
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert "+VALUE = 4" in reviewer.calls[1][0]
    assert "-VALUE = 3" in reviewer.calls[1][0]


def test_a_reset_past_the_approval_reviews_against_head(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    _commit(repo, "work")
    _edit_strict(repo, "VALUE = 5\n")
    reviewer = FakeReviewer([[], []])
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    git(repo, "reset", "-q", "--hard", "HEAD~1")
    _edit_strict(repo, "VALUE = 4\n")
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert "-VALUE = 1" in reviewer.calls[1][0]
    assert "+VALUE = 4" in reviewer.calls[1][0]


def test_a_commit_made_while_blocked_is_still_reviewed(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    reviewer = FakeReviewer([["first"], []])
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    _commit(repo, "sneaked in")
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert "+VALUE = 3" in reviewer.calls[1][0]


def test_a_deletion_is_reviewed_without_its_old_body(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "strict" / "core.py").unlink()
    (repo / "pkg" / "strict" / "fresh.py").write_text("FRESH = 1\n", encoding="utf-8")
    reviewer = FakeReviewer([[]])
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    prompt = reviewer.calls[0][0]
    assert "deleted file mode" in prompt
    assert "-VALUE = 1" not in prompt


def test_findings_block_the_stop_and_are_handed_over(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    reviewer = FakeReviewer([["VALUE says nothing"]])
    outcome = review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert isinstance(outcome, Block)
    assert "pkg/strict/core.py:1 [bad-name] VALUE says nothing" in outcome.reason
    assert outcome.payload()["decision"] == "block"
    assert load_state(repo, HOOK_STATE_FILE).blocked_rounds == 1


def test_a_blocked_round_reviews_the_whole_diff_again(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo, "VALUE = 3\n")
    reviewer = FakeReviewer([["first"], []])
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    _edit_strict(repo, "VALUE = 4\n")
    review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert "+VALUE = 4" in reviewer.calls[1][0]
    assert "-VALUE = 1" in reviewer.calls[1][0]


def test_the_third_round_goes_to_the_tiebreak_model(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    reviewer = FakeReviewer([["one"], ["two"], [], []])
    for body in ("VALUE = 3\n", "VALUE = 4\n", "VALUE = 5\n", "VALUE = 6\n"):
        _edit_strict(repo, body)
        review_gate.hook_decision(repo, _stop(repo), reviewer)
    models = [model for _, model in reviewer.calls]
    assert models == [
        review_gate.PRIMARY_MODEL,
        review_gate.PRIMARY_MODEL,
        review_gate.TIEBREAK_MODEL,
        review_gate.PRIMARY_MODEL,
    ]
    assert load_state(repo, HOOK_STATE_FILE).blocked_rounds == 0


def test_the_gate_gives_up_at_the_round_cap_and_starts_the_count_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    monkeypatch.setattr(review_gate, "MAX_BLOCKED_ROUNDS", 3)
    reviewer = FakeReviewer([["stuck"]] * 4)
    outcomes = [review_gate.hook_decision(repo, _stop(repo), reviewer) for _ in range(4)]
    assert [type(outcome) for outcome in outcomes] == [Block, Block, GiveUp, Block]
    released = outcomes[2]
    assert isinstance(released, GiveUp)
    assert "gave up after 3 blocked rounds" in released.message
    assert "[bad-name] stuck" in released.payload()["systemMessage"]
    assert reviewer.calls[3][1] == review_gate.PRIMARY_MODEL
    assert "+VALUE = 3" in reviewer.calls[3][0]


def test_a_reviewer_that_cannot_run_blocks_the_stop_and_counts_no_round(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    outcome = review_gate.hook_decision(repo, _stop(repo), broken_reviewer)
    assert isinstance(outcome, Block)
    assert "failed on batch 1 of 1: quota exhausted" in outcome.reason
    assert load_state(repo, HOOK_STATE_FILE) == EMPTY_STATE


def _budget(monkeypatch: pytest.MonkeyPatch, diff_chars: int) -> None:
    rubric = review_gate.RUBRIC_PATH.read_text(encoding="utf-8")
    tokens = (len(rubric) + diff_chars) // review_gate.CHARS_PER_TOKEN
    monkeypatch.setattr(review_gate, "PROMPT_BUDGET_TOKENS", tokens)


def test_a_diff_over_the_budget_is_reviewed_in_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "strict" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "pkg" / "strict" / "b.py").write_text("B = 1\n", encoding="utf-8")
    _budget(monkeypatch, 200)
    reviewer = FakeReviewer([[], []])
    assert review_gate.hook_decision(repo, _stop(repo), reviewer) is None
    prompts = [prompt for prompt, _ in reviewer.calls]
    assert ["+A = 1" in prompt for prompt in prompts] == [True, False]
    assert ["+B = 1" in prompt for prompt in prompts] == [False, True]


def test_a_file_whose_diff_alone_is_over_the_budget_is_too_large(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "strict" / "huge.py").write_text("HUGE = 1\n" * 50, encoding="utf-8")
    _budget(monkeypatch, 200)
    reviewer = FakeReviewer([])
    outcome = review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert isinstance(outcome, Block)
    assert "pkg/strict/huge.py:1 [too-large]" in outcome.reason
    assert reviewer.calls == []


def test_a_failed_batch_blocks_on_what_was_found_and_counts_no_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "strict" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "pkg" / "strict" / "b.py").write_text("B = 1\n", encoding="utf-8")
    _budget(monkeypatch, 200)
    reviewer = FakeReviewer([["A says nothing"]])
    outcome = review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert isinstance(outcome, Block)
    assert "the reviewer ran out of quota" in outcome.reason
    assert "pkg/strict/core.py:1 [bad-name] A says nothing" in outcome.reason
    assert load_state(repo, HOOK_STATE_FILE) == EMPTY_STATE


def test_a_failed_batch_after_a_clean_one_still_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "strict" / "a.py").write_text("A = 1\n", encoding="utf-8")
    (repo / "pkg" / "strict" / "b.py").write_text("B = 1\n", encoding="utf-8")
    _budget(monkeypatch, 200)
    outcome = review_gate.hook_decision(repo, _stop(repo), FakeReviewer([[]]))
    assert isinstance(outcome, Block)
    assert "batch 2 of 2: the reviewer ran out of quota" in outcome.reason
    assert load_state(repo, HOOK_STATE_FILE) == EMPTY_STATE


def test_a_diff_needing_more_batches_than_the_cap_is_too_large(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = strict_repo(tmp_path)
    for name in ("a", "b", "c"):
        (repo / "pkg" / "strict" / f"{name}.py").write_text(f"{name.upper()} = 1\n", encoding="utf-8")
    _budget(monkeypatch, 200)
    monkeypatch.setattr(review_gate, "MAX_BATCHES", 2)
    reviewer = FakeReviewer([])
    outcome = review_gate.hook_decision(repo, _stop(repo), reviewer)
    assert isinstance(outcome, Block)
    assert "[too-large] the change needs 3 review batches, over the cap of 2" in outcome.reason
    assert reviewer.calls == []


def test_review_from_a_base_covers_every_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = strict_repo(tmp_path)
    (repo / "pkg" / "loose" / "other.py").write_text("VALUE = 9\n", encoding="utf-8")
    reviewer = FakeReviewer([["loose is loose"]])
    assert review_gate.review_from(repo, "HEAD", reviewer) == 1
    assert "+VALUE = 9" in reviewer.calls[0][0]
    out = capsys.readouterr().out
    assert out.startswith(f"verdict: block ({review_gate.PRIMARY_MODEL}, 1 files since HEAD)")
    assert "[bad-name] loose is loose" in out


def test_review_from_a_base_leaves_the_hook_state_alone(tmp_path: Path) -> None:
    repo = strict_repo(tmp_path)
    _edit_strict(repo)
    review_gate.review_from(repo, "HEAD", FakeReviewer([["first"]]))
    assert load_state(repo, HOOK_STATE_FILE) == EMPTY_STATE
    assert load_state(repo, BASE_STATE_FILE).blocked_rounds == 1


def test_review_from_a_base_with_no_change_passes_unreviewed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = strict_repo(tmp_path)
    reviewer = FakeReviewer([])
    assert review_gate.review_from(repo, "HEAD", reviewer) == 0
    assert capsys.readouterr().out == "verdict: pass (nothing changed since HEAD)\n"
