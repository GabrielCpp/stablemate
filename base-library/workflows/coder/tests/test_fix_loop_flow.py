"""Integration tests for the inline fix-drain detour (`select_fix_item` through
`decide_post_drain`) wired between `decide_post_sentinel` and each mode's commit node.

Covers the graph edges per the plan's verification point 2:
  - backlog-empty falls straight through `decide_post_drain` to the correct commit
    node for each mode (story → commit_story_pr, epic → commit_story), with none
    of the fix-loop's story-producing nodes ever running.
  - a passed outcome (`check_fix`) reaches `prune_fix_item`, removes the bullet,
    and loops back through `select_fix_item` to the correct commit node.
  - a failed-after-retry outcome (`check_fix` fails, `apply_fix_once` +
    `recheck_fix` still fails) reaches `fix_give_up`, annotates the bullet
    `(blocked: ...)` in place without removing it, does not halt the run, and
    still reaches the correct commit node.
  - regression check: after a fix drains, `commit_story`/`commit_story_pr` still
    commit under the ORIGINAL story's identity (`prepare_story`'s story_slug/epic),
    not the fix's own (`prepare_fix_story`'s) — the node-id-clobbering hazard the
    plan flagged.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from workhorse.testing import WorkflowRun, assert_step_output, assert_json_file

from conftest import (
    WORKFLOW,
    make_epic,
    make_queue,
    git_mock_no_remote,
    mock_all_agents_happy,
    mock_documentation_happy,
    mock_ostler_fix_passthrough,
    story_params,
)


def _backlog(sandbox: Path, text: str) -> Path:
    p = sandbox / "docs" / "backlog.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _filed_bullet(bullet_id: str, text: str) -> str:
    return f"# Backlog\n\n## Filed by coder\n\n- [{bullet_id}] {text}\n"


def _commit_messages(result, node_id: str | None = None) -> list[str]:  # noqa: ARG001
    """Commit subjects recorded in the real throwaway git repo."""
    repo = result.test_dir.parent
    proc = subprocess.run(
        ["git", "log", "--pretty=%s"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.splitlines()


def _mock_fix_agents_happy(wf: WorkflowRun) -> None:
    wf.mock_agent("plan_fix", {"plan_result": {"status": "done", "summary": "Fix planned."}})
    wf.mock_agent("implement_fix", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent("check_fix", {"qa_result": {"status": "passed", "notes": ""}})
    mock_documentation_happy(wf)


def _fix_params(sandbox: Path) -> dict:
    return {"docs_path": str(sandbox)}


_ENCLOSING_STORY_NODES = (
    "init_base", "branch_story", "select_epic", "select_story",
    "commit_story", "commit_story_pr",
)


# ---------------------------------------------------------------------------
# Backlog-empty pass-through
# ---------------------------------------------------------------------------


def test_empty_backlog_story_mode_skips_fix_loop(story_sandbox, monkeypatch):
    """No docs/backlog.md at all: select_fix_item draws nothing, decide_post_drain
    falls straight through to commit_story_pr — the original story-mode commit path,
    unchanged from before the fix loop existed."""
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch)
    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_fix_item", "has_fix", "no")
    assert_step_output(result, "commit_story_pr", "committed", "yes")
    assert_step_output(result, "open_story_pr", "story_pr", "skipped")

    # None of the story-producing fix-loop nodes ever ran.
    assert result.step_outputs("seed_fix_story") == {}
    assert result.step_outputs("prune_fix_item") == {}
    assert result.step_outputs("fix_give_up") == {}
    assert [c for c in result.calls("claude") if c["node_id"] == "plan_fix"] == []


def test_empty_backlog_epic_mode_skips_fix_loop(tmp_path, monkeypatch):
    """Same pass-through in epic mode: decide_post_drain routes to commit_story."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-1"])
    story_md = tmp_path / "docs" / "epics" / "epic-1" / "stories" / "s-1" / "story.md"

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_all_agents_happy(wf, monkeypatch, story_md_paths=[story_md])
    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_fix_item", "has_fix", "no")
    assert_step_output(result, "commit_story", "committed", "yes")
    assert_json_file(tmp_path, "docs/epics/epics-todo.json", [])
    assert result.step_outputs("seed_fix_story") == {}


# ---------------------------------------------------------------------------
# Passed drain
# ---------------------------------------------------------------------------


def test_fix_loop_drains_passed_item_story_mode(story_sandbox, monkeypatch):
    """One filed bullet, check_fix passes first try: prune_fix_item removes it,
    the loop returns to select_fix_item (now empty), and the run still commits
    under the ORIGINAL story's identity (story_slug s-1), not the fix's own."""
    _backlog(story_sandbox, _filed_bullet("bug-a", "Fix the flaky sentinel gate"))

    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch, ostler_setup=mock_ostler_fix_passthrough)
    _mock_fix_agents_happy(wf)
    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "prune_fix_item", "pruned", "yes")
    assert_step_output(result, "prune_fix_item", "bullet_id", "bug-a")
    # Loop converges: the LAST select_fix_item call (after pruning) sees an empty backlog.
    assert_step_output(result, "select_fix_item", "has_fix", "no")

    body = (story_sandbox / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "[bug-a]" not in body

    # Never retried or gave up — this was a first-try pass.
    assert result.step_outputs("apply_fix_once") == {}
    assert result.step_outputs("fix_give_up") == {}

    # Regression check: commit_story_pr still commits the ORIGINAL story (s-1),
    # not the fix's own story (which would live under the "fixes" epic).
    assert_step_output(result, "commit_story_pr", "committed", "yes")
    messages = _commit_messages(result)
    assert "s-1" in messages
    assert not any("fixes" in m for m in messages)


def test_fix_loop_drains_passed_item_epic_mode(tmp_path, monkeypatch):
    """Same passed-drain scenario in epic mode: commit_story keeps committing under
    the epic's own story identity ("epic-1: s-1"), not the fix's."""
    make_epic(tmp_path, "epic-1", [{"slug": "s-1", "status": "In progress"}])
    make_queue(tmp_path, ["epic-1"])
    story_md = tmp_path / "docs" / "epics" / "epic-1" / "stories" / "s-1" / "story.md"
    _backlog(tmp_path, _filed_bullet("bug-a", "Fix the flaky sentinel gate"))

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_all_agents_happy(
        wf, monkeypatch, story_md_paths=[story_md], ostler_setup=mock_ostler_fix_passthrough
    )
    _mock_fix_agents_happy(wf)
    result = wf.run()

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "prune_fix_item", "pruned", "yes")
    body = (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "[bug-a]" not in body

    assert_step_output(result, "commit_story", "committed", "yes")
    messages = _commit_messages(result)
    assert "epic-1: s-1" in messages
    assert not any(m.startswith("fixes:") for m in messages)


# ---------------------------------------------------------------------------
# Failed-after-retry gives up without halting
# ---------------------------------------------------------------------------


def test_fix_loop_gives_up_after_one_retry_without_halting(story_sandbox, monkeypatch):
    """check_fix fails, the one bounded retry (apply_fix_once → recheck_fix) still
    fails: fix_give_up annotates the bullet in place (not removed), the run does
    NOT halt, and the story's own commit still proceeds normally."""
    _backlog(story_sandbox, _filed_bullet("bug-a", "Fix the flaky sentinel gate"))

    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch, ostler_setup=mock_ostler_fix_passthrough)
    wf.mock_agent("plan_fix", {"plan_result": {"status": "done", "summary": "Fix planned."}})
    wf.mock_agent("implement_fix", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent("check_fix", {"qa_result": {"status": "failed", "notes": "still broken"}})
    wf.mock_agent("apply_fix_once", {"qa_result": {"status": "applied", "notes": ""}})
    wf.mock_agent("recheck_fix", {"qa_result": {"status": "failed", "notes": "still broken"}})
    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "fix_give_up", "marked", "yes")
    assert_step_output(result, "fix_give_up", "bullet_id", "bug-a")
    assert result.step_outputs("prune_fix_item") == {}

    body = (story_sandbox / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "[bug-a]" in body, "a blocked fix stays visible in the backlog, never deleted"
    assert "(blocked:" in body
    assert body.count("(blocked:") == 1

    # Exactly one retry — apply_fix_once/recheck_fix each ran once, not looped.
    apply_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_fix_once"]
    recheck_calls = [c for c in result.calls("claude") if c["node_id"] == "recheck_fix"]
    assert len(apply_calls) == 1
    assert len(recheck_calls) == 1

    # The story's own commit still lands (blocked fix never halts the run).
    assert_step_output(result, "commit_story_pr", "committed", "yes")
    messages = _commit_messages(result)
    assert "s-1" in messages


# ---------------------------------------------------------------------------
# Standalone "fix" flow: a drain-only entry point, no enclosing epic/story.
# Run via `workhorse run coder fix`, i.e. `wf.run(flow="fix", ...)` here — a
# self-contained sub-graph (its own node namespace, its own run dir), NOT the
# `mode` var on the main graph. `_ENCLOSING_STORY_NODES` don't even exist in
# this flow's namespace, so those assertions are a cheap structural guard that
# this flow never touches the main graph's story-selection machinery.
# ---------------------------------------------------------------------------


def test_standalone_fix_mode_empty_backlog_is_a_noop(tmp_path):
    """Nothing to drain: select_fix_item draws nothing and decide_fix_item's
    `no` case goes straight to this flow's own `done` terminal — none of the
    epic/story machinery (no epic/story selected, no branch cut) ever runs."""
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    git_mock_no_remote(tmp_path)

    wf = WorkflowRun(WORKFLOW, tmp_path)
    result = wf.run(flow="fix", params=_fix_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "select_fix_item", "has_fix", "no")
    for node in _ENCLOSING_STORY_NODES:
        assert result.step_outputs(node) == {}, f"{node} must not run in the standalone fix flow"


def test_standalone_fix_mode_drains_passed_item_and_commits_it(tmp_path, monkeypatch):
    """One filed bullet, check_fix passes first try: commit_fix_item commits it
    directly (no enclosing story commit exists in this flow), tagged with the
    self-created "fixes" epic identity, then the drain converges to empty and
    the run stops — still without ever touching epic/story selection."""
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    _backlog(tmp_path, _filed_bullet("bug-a", "Fix the flaky sentinel gate"))
    git_mock_no_remote(tmp_path)

    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_ostler_fix_passthrough(monkeypatch)
    _mock_fix_agents_happy(wf)
    result = wf.run(flow="fix", params=_fix_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "prune_fix_item", "pruned", "yes")
    assert_step_output(result, "commit_fix_item", "committed", "yes")
    assert_step_output(result, "select_fix_item", "has_fix", "no")

    body = (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "[bug-a]" not in body

    messages = _commit_messages(result)
    assert any(m.startswith("fixes:") for m in messages)
    for node in _ENCLOSING_STORY_NODES:
        assert result.step_outputs(node) == {}


def test_standalone_fix_mode_commits_blocked_item_too(tmp_path, monkeypatch):
    """check_fix fails, the one bounded retry still fails: fix_give_up annotates
    the bullet in place, and commit_fix_item STILL commits (the "commit whatever
    happened" rule the enclosing story's commit would apply anyway) — the run
    doesn't halt and doesn't lose the blocked-annotation edit."""
    (tmp_path / "docs" / "epics").mkdir(parents=True)
    _backlog(tmp_path, _filed_bullet("bug-a", "Fix the flaky sentinel gate"))
    git_mock_no_remote(tmp_path)

    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_ostler_fix_passthrough(monkeypatch)
    mock_documentation_happy(wf)
    wf.mock_agent("plan_fix", {"plan_result": {"status": "done", "summary": "Fix planned."}})
    wf.mock_agent("implement_fix", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent("check_fix", {"qa_result": {"status": "failed", "notes": "still broken"}})
    wf.mock_agent("apply_fix_once", {"qa_result": {"status": "applied", "notes": ""}})
    wf.mock_agent("recheck_fix", {"qa_result": {"status": "failed", "notes": "still broken"}})
    result = wf.run(flow="fix", params=_fix_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "fix_give_up", "marked", "yes")
    assert_step_output(result, "commit_fix_item", "committed", "yes")
    assert result.step_outputs("prune_fix_item") == {}

    body = (tmp_path / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "[bug-a]" in body
    assert "(blocked:" in body
