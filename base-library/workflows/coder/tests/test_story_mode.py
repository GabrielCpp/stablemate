"""Tests for story mode (mode=story) execution paths.

Story mode skips the epic queue and CI/merge machinery: the caller provides
story_path, spec_dir, story_slug, and epic directly. The workflow
cuts a per-story branch (the bare story id), runs the plan → implement → review → QA
pipeline once (no separate plan-review agent), commits, and opens a PR at the end —
but never merges it (the PR is left open for a human).

Paths covered:
  - Happy path — all stages pass on first attempt → done (exit 0)
  - Plan directly blocked — plan returns blocked → gate_plan → await_operator blocks
  - Operator answered, scope=story — ANSWERED context.md → rework_plan → implement
  - Operator answered, scope=epic — ANSWERED context.md + SCOPE: epic →
    replan_epic → select_story (empty queue) → done (exit 0)
  - Implementation review loop — review_implementation needs_changes → apply_review → approved
  - QA fails then self-fixes — qa fails, apply_qa_fixes passes → done
  - QA max rework → qa_failed — qa always fails → exit non-zero
"""

from __future__ import annotations

from workhorse.graph.loader import load_workflow
from workhorse.testing import (
    WorkflowRun,
    assert_step_output,
)

from conftest import (
    WORKFLOW,
    mock_all_agents_happy,
    mock_qa_control_plane,
    mock_ostler_qa,
    story_params,
    git_mock_no_remote,
)

OPERATOR_BLOCK_TIMEOUT = 60


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_happy_path(story_sandbox, monkeypatch):
    """All agents approve on the first try → workflow completes, exit 0."""
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch)
    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert result.step_outputs("run_qa_plan")["qa_result"]["status"] == "passed"
    assert_step_output(
        result, "implement_layer", "impl_result", {"status": "done", "notes": ""}
    )


def test_story_mode_branches_and_opens_pr_no_merge(story_sandbox, monkeypatch):
    """Story mode runs on a <slug> branch and opens a PR at the end — no merge.

    Offline (no token): branch_story names the branch after the story id and
    open_story_pr is reached (skipped, since there's no remote/token) — proving the
    run terminates via the story-PR path, never the epic merge.
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_all_agents_happy(wf, monkeypatch)
    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    # branch is named after the story id (<slug>), not feat/<epic>
    assert_step_output(result, "branch_story", "story_branch", "s-1")
    # the story PR step ran as the terminal step (offline → skipped, but reached)
    assert_step_output(result, "open_story_pr", "story_pr", "skipped")


def test_open_story_pr_consumes_the_cut_branch():
    """open_story_pr must take its branch from branch_story, never re-derive it.

    Regression guard: these two drifted once. branch-story.py cut the bare story
    id while open-story-pr.py rebuilt the name with a `story/` prefix, so every
    story-mode PR targeted a branch that had never been cut. Both agree today,
    which is exactly why a value-equality test would pass either way — the
    invariant worth pinning is the *wiring*, not the current string.
    """
    g = load_workflow(WORKFLOW)
    args = g.nodes["open_story_pr"].args

    assert "get_node_output('branch_story', 'story_branch')" in " ".join(args), (
        "open_story_pr must consume branch_story's story_branch output; "
        f"got args={args}"
    )
    # branch_story must actually publish it (the arg above is silently "" otherwise).
    assert "story_branch" in {o.key for o in g.nodes["branch_story"].outputs}


# ---------------------------------------------------------------------------
# 2. Plan directly blocked → operator blocks
# ---------------------------------------------------------------------------
# (There is no separate plan-review agent and no needs_rework loop anymore: the plan
# goes straight to implementation unless it returns `blocked` itself, which gates.)


def test_plan_blocked_operator_gate_blocks(story_sandbox, monkeypatch):
    """plan blocked → the operator gate BLOCKS in place instead of exiting.

    The gate used to exit(2), which tore down the Docker container. Now the groom
    sidecar lives *in* that container, so the gate must keep the run alive: it writes
    an AWAITING context.md and blocks for the operator rather than halting. Without an
    answer the run therefore never advances — it just waits (here the harness times it
    out), and rework_plan is never reached.
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_ostler_qa(monkeypatch)
    wf.mock_agent(
        "plan",
        {"plan_result": {"status": "blocked", "summary": "Environment missing."}},
    )
    # No operator answer → the gate blocks; the run does not exit on its own.
    result = wf.run(params=story_params(story_sandbox), timeout=OPERATOR_BLOCK_TIMEOUT)

    assert result.exit_code == -1, (
        "the operator gate must block (keeping the container alive), not exit\n"
        f"exit_code={result.exit_code}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # It wrote an AWAITING context.md for the operator to answer.
    ctx = story_sandbox / "docs" / "epics" / "epic-1" / "stories" / "s-1" / "context.md"
    assert ctx.is_file(), "gate should have written a context.md for the operator"
    assert "AWAITING_OPERATOR" in ctx.read_text(encoding="utf-8")
    # And it did not advance past the gate without an answer.
    rework_calls = [c for c in result.calls("claude") if c["node_id"] == "rework_plan"]
    assert rework_calls == [], "rework_plan should not run without an operator answer"


# ---------------------------------------------------------------------------
# 4. Operator answered, scope=story → rework then approved
# ---------------------------------------------------------------------------


def test_operator_answered_scope_story_reworks_then_done(story_sandbox, monkeypatch):
    """Pre-populated ANSWERED context.md (scope=story) → rework proceeds, plan approved."""
    params = story_params(story_sandbox)
    story_dir = story_sandbox / "docs" / "epics" / "epic-1" / "stories" / "s-1"
    context_md = story_dir / "context.md"
    context_md.write_text(
        "STATUS: ANSWERED\n"
        "SCOPE: story\n\n"
        "## Your answers\n\nPlease simplify the plan scope.\n",
        encoding="utf-8",
    )

    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    # plan → blocked triggers await_operator, which finds the ANSWERED context.md;
    # decide_operator_scope (scope=story) → rework_plan → decide_plan(done) → implement.
    wf.mock_agent(
        "plan", {"plan_result": {"status": "blocked", "summary": "Need clarification."}}
    )
    wf.mock_agent(
        "rework_plan", {"plan_result": {"status": "done", "summary": "Simplified."}}
    )
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch)
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(params=params)

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    # rework_plan must have been called once (from the ANSWERED → scope=story path)
    rework_calls = [c for c in result.calls("claude") if c["node_id"] == "rework_plan"]
    assert rework_calls, "rework_plan should have been called after operator answered"


# ---------------------------------------------------------------------------
# 5. Operator answered, scope=epic → replan_epic → select_story (empty queue)
# ---------------------------------------------------------------------------


def test_operator_answered_scope_epic_replans_then_done(story_sandbox, monkeypatch):
    """ANSWERED context.md + SCOPE: epic → replan_epic → select_story (no queue) → done."""
    params = story_params(story_sandbox)
    story_dir = story_sandbox / "docs" / "epics" / "epic-1" / "stories" / "s-1"
    (story_dir / "context.md").write_text(
        "STATUS: ANSWERED\nSCOPE: epic\n\n## Your answers\n\nRevise the entire epic.\n",
        encoding="utf-8",
    )

    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    mock_ostler_qa(monkeypatch)
    # plan → blocked triggers await_operator, which finds ANSWERED + SCOPE: epic →
    # decide_operator_scope (epic) → replan_epic → select_story (empty queue) → done.
    wf.mock_agent(
        "plan", {"plan_result": {"status": "blocked", "summary": "Epic scope wrong."}}
    )
    wf.mock_agent(
        "replan_epic", {"replan_result": {"status": "done", "summary": "Replanned."}}
    )
    result = wf.run(params=params)

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    replan_calls = [c for c in result.calls("claude") if c["node_id"] == "replan_epic"]
    assert replan_calls, "replan_epic should have been called"


# ---------------------------------------------------------------------------
# 6. Implementation review loop — needs_changes once, then approved
# ---------------------------------------------------------------------------


def test_impl_review_needs_changes_then_approved(story_sandbox, monkeypatch):
    """review_implementation returns needs_changes → apply_review → then approved."""
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent_sequence(
        "review_implementation",
        [
            {
                "review_impl_result": {
                    "status": "needs_changes",
                    "notes": "Fix imports.",
                }
            },
            {"review_impl_result": {"status": "approved", "notes": ""}},
        ],
    )
    wf.mock_agent("apply_review", {"impl_result": {"status": "applied", "notes": ""}})
    mock_qa_control_plane(wf, monkeypatch)
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    apply_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_review"]
    assert apply_calls, "apply_review should have been called once"
    assert result.step_outputs("run_qa_plan")["qa_result"]["status"] == "passed"


# ---------------------------------------------------------------------------
# 8. Review remediation: apply_review is settled deterministically, not re-reviewed
# ---------------------------------------------------------------------------


def test_impl_review_apply_settles_without_rereview(story_sandbox, monkeypatch):
    """needs_changes → apply_review → deterministic settle → QA, with NO re-review.

    The review loop was redesigned (verify_review_resolution): once apply_review's
    resolution verifies as `applied`, the loop approves and EXITS to QA — it does NOT
    re-run review_implementation, which is what used to let the reviewer re-litigate
    already-settled findings and move goalposts (the deterministic settle IS the
    re-verify). With no `review-resolution.json` verdict in the sandbox, the gate is a
    pass-through, so a single needs_changes → apply cycle proceeds straight to QA.

    review_implementation is mocked to ALWAYS return needs_changes: if the loop
    regressed to re-reviewing after each apply, it would spin to the guard_review cap
    and halt at the operator gate (exit 2) instead of passing — so `result.passed()`
    plus a single review/apply pair is the guard against that regression.
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "needs_changes", "notes": "Fix imports."}},
    )
    wf.mock_agent("apply_review", {"impl_result": {"status": "applied", "notes": ""}})
    mock_qa_control_plane(wf, monkeypatch)
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    apply_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_review"]
    assert len(apply_calls) == 1, (
        f"Expected 1 apply_review call, got {len(apply_calls)}"
    )
    # No re-review after the settle: review_implementation runs exactly once.
    review_calls = [
        c for c in result.calls("claude") if c["node_id"] == "review_implementation"
    ]
    assert len(review_calls) == 1, (
        f"Expected 1 review_implementation call, got {len(review_calls)}"
    )
    assert result.step_outputs("run_qa_plan")["qa_result"]["status"] == "passed"


# ---------------------------------------------------------------------------
# 9. QA fails then self-fixes
# ---------------------------------------------------------------------------


def test_qa_fails_then_apply_fixes_passes(story_sandbox, monkeypatch):
    """qa fails first → apply_qa_fixes runs → qa RE-RUNS and passes → workflow completes.

    The fix loop no longer trusts apply_qa_fixes's self-reported status: after a fix it re-runs
    qa (→ verify_qa gate → audit_qa) so only a freshly gated+audited pass can exit the loop. So a
    success here needs the qa mock to return failed-then-passed, not apply_qa_fixes saying "passed".
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["failed", "passed"])
    wf.mock_agent(
        "apply_qa_fixes", {"qa_result": {"status": "passed", "notes": "Fixed."}}
    )
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    fix_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]
    assert fix_calls, "apply_qa_fixes should have been called"
    assert (result.test_dir / "qa-run-count.txt").read_text() == "2"


def test_semantic_plan_review_revises_before_execution(story_sandbox, monkeypatch):
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch)
    wf.mock_agent_sequence(
        "review_qa_plan",
        [
            {
                "qa_plan_review": {
                    "disposition": "revise",
                    "notes": "The final assertion does not prove persistence.",
                }
            },
            {
                "qa_plan_review": {
                    "disposition": "approved",
                    "notes": "Persistence is now observed after reload.",
                }
            },
        ],
    )
    wf.mock_agent(
        "audit_qa",
        {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": ""}},
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), result.stderr
    assert len([c for c in result.calls("claude") if c["node_id"] == "plan_qa"]) == 2
    assert (result.test_dir / "qa-run-count.txt").read_text() == "1"


def test_plan_revisions_do_not_consume_product_fix_budget(story_sandbox, monkeypatch):
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["failed", "passed"])
    wf.mock_agent_sequence(
        "review_qa_plan",
        [
            {
                "qa_plan_review": {
                    "disposition": "revise",
                    "notes": f"Semantic revision {index}",
                }
            }
            for index in range(3)
        ]
        + [
            {
                "qa_plan_review": {
                    "disposition": "approved",
                    "notes": "Semantically complete.",
                }
            },
            {
                "qa_plan_review": {
                    "disposition": "approved",
                    "notes": "Semantically complete after product fix.",
                }
            },
        ],
    )
    wf.mock_agent("triage_qa", {"triage_action": "qa_fix", "qa_failure_class": "code"})
    wf.mock_agent(
        "apply_qa_fixes", {"qa_result": {"status": "applied", "notes": "Fixed product."}}
    )
    wf.mock_agent(
        "audit_qa",
        {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": ""}},
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), result.stderr
    assert result.step_outputs("incr_qa_plan")["qa_plan_rework_count"]["value"] == 3
    assert result.step_outputs("incr_qa")["qa_rework_count"]["value"] == 1
    assert len([c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]) == 1


def test_run_assessment_repairs_plan_when_objective_not_reached(story_sandbox, monkeypatch):
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["passed", "passed"])
    wf.mock_agent_sequence(
        "assess_qa_run",
        [
            {
                "qa_assessment": {
                    "disposition": "repair_plan",
                    "failure_class": "plan",
                    "objective_reached": "no",
                    "notes": "The browser deep-linked past the failing navigation chain.",
                }
            },
            {
                "qa_assessment": {
                    "disposition": "confirmed",
                    "failure_class": "none",
                    "objective_reached": "yes",
                    "notes": "Normal navigation and terminal objective were observed.",
                }
            },
        ],
    )
    wf.mock_agent(
        "audit_qa",
        {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": ""}},
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), result.stderr
    assert (result.test_dir / "qa-run-count.txt").read_text() == "2"
    assert len([c for c in result.calls("claude") if c["node_id"] == "plan_qa"]) == 2


def test_run_assessment_product_diagnosis_enters_fix_loop(story_sandbox, monkeypatch):
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["passed", "passed"])
    wf.mock_agent_sequence(
        "assess_qa_run",
        [
            {
                "qa_assessment": {
                    "disposition": "confirmed",
                    "failure_class": "product",
                    "objective_reached": "yes",
                    "notes": "The captured response contains an unexpected server error.",
                }
            },
            {
                "qa_assessment": {
                    "disposition": "confirmed",
                    "failure_class": "none",
                    "objective_reached": "yes",
                    "notes": "The corrected objective completed without errors.",
                }
            },
        ],
    )
    wf.mock_agent("triage_qa", {"triage_action": "qa_fix", "qa_failure_class": "code"})
    wf.mock_agent(
        "apply_qa_fixes", {"qa_result": {"status": "applied", "notes": "Fixed server error."}}
    )
    wf.mock_agent(
        "audit_qa",
        {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": ""}},
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), result.stderr
    assert result.step_outputs("mark_qa_assessment_failed")["qa_result"]["status"] == "failed"
    assert len([c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]) == 1
    assert (result.test_dir / "qa-run-count.txt").read_text() == "2"


def test_product_audit_refutation_enters_fix_loop(story_sandbox, monkeypatch):
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["passed", "passed"])
    wf.mock_agent_sequence(
        "audit_qa",
        [
            {
                "qa_audit": {
                    "verdict": "refuted",
                    "refutation_class": "product-contradiction",
                    "notes": "Reload evidence shows the old value.",
                }
            },
            {
                "qa_audit": {
                    "verdict": "stands",
                    "refutation_class": "none",
                    "notes": "The corrected evidence stands.",
                }
            },
        ],
    )
    wf.mock_agent("triage_qa", {"triage_action": "qa_fix", "qa_failure_class": "code"})
    wf.mock_agent(
        "apply_qa_fixes", {"qa_result": {"status": "applied", "notes": "Fixed persistence."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), result.stderr
    assert result.step_outputs("mark_qa_audit_failed")["qa_result"]["status"] == "failed"
    assert len([c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]) == 1
    assert (result.test_dir / "qa-run-count.txt").read_text() == "2"


# ---------------------------------------------------------------------------
# 10. QA fails twice then passes (multi-rework success)
# ---------------------------------------------------------------------------


def test_qa_fails_twice_then_passes(story_sandbox, monkeypatch):
    """qa fails twice (re-running after each fix) then passes on the third run → done.

    Each qa pass is re-validated by re-running qa after apply_qa_fixes (the gate + auditor must
    re-approve), so the qa mock itself drives the failed→failed→passed sequence and two fix cycles
    run before qa finally passes.
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["failed", "failed", "passed"])
    wf.mock_agent("apply_qa_fixes", {"qa_result": {"status": "applied", "notes": ""}})
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    fix_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]
    assert len(fix_calls) == 2, f"Expected 2 apply_qa_fixes calls, got {len(fix_calls)}"


# ---------------------------------------------------------------------------
# 11. QA max rework → qa_failed (story mode terminal)
# ---------------------------------------------------------------------------


def test_qa_max_rework_reaches_qa_failed(story_sandbox, monkeypatch):
    """qa always fails → 3 apply_qa_fixes attempts → qa_failed terminal → exit non-zero."""
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["failed"])
    wf.mock_agent(
        "apply_qa_fixes", {"qa_result": {"status": "failed", "notes": "Still failing."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert not result.passed(), "Expected workflow to fail after max QA reworks"
    fix_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]
    assert len(fix_calls) == 3, f"Expected 3 apply_qa_fixes calls, got {len(fix_calls)}"


# ---------------------------------------------------------------------------
# 12. QA blocked on the environment → setup_fix makes it runnable → re-QA passes
# ---------------------------------------------------------------------------


def test_qa_blocked_setup_fix_ready_then_passes(story_sandbox, monkeypatch):
    """qa blocked (dev stack down) → setup_fix reports ready → qa RE-RUNS and passes → done.

    An environment block routes to setup_fix, NOT the code-fix loop: the stack is made runnable and
    QA re-runs. apply_qa_fixes is never called — it was a setup problem, not a code defect.
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["blocked", "passed"])
    wf.mock_agent(
        "setup_fix",
        {
            "setup_result": {
                "status": "ready",
                "notes": "Started emulators + dev server.",
            }
        },
    )
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    setup_calls = [c for c in result.calls("claude") if c["node_id"] == "setup_fix"]
    assert len(setup_calls) == 1, f"setup_fix should run once, got {len(setup_calls)}"
    assert (result.test_dir / "qa-run-count.txt").read_text() == "2"
    fix_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]
    assert not fix_calls, "apply_qa_fixes must NOT run for an environment block"


# ---------------------------------------------------------------------------
# 13. QA stays blocked despite setup_fix → bounded loop escalates to operator
# ---------------------------------------------------------------------------


def test_qa_failed_triage_rescope_reenters_dev_then_passes(story_sandbox, monkeypatch):
    """qa fails → triage_qa returns `rescope` → the story re-enters dev (plan+implement),
    re-runs review + QA, and passes → done.

    This is the fix-forward path: instead of the in-AC apply_qa_fixes loop, the triager
    scoped adjacent defects/hardening INTO the story (ACs amended on disk) and asked to
    re-implement. The parent decide_qa_outcome `rescope` case routes back to the dev flow,
    so plan runs a second time and apply_qa_fixes is never touched.
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["failed", "passed"])
    wf.mock_agent("triage_qa", {"triage_action": "rescope", "qa_failure_class": "code"})
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    triage_calls = [c for c in result.calls("claude") if c["node_id"] == "triage_qa"]
    assert len(triage_calls) == 1, f"triage_qa should run once, got {len(triage_calls)}"
    plan_calls = [c for c in result.calls("claude") if c["node_id"] == "plan"]
    assert len(plan_calls) == 2, (
        f"plan should run twice (initial + rescope re-entry), got {len(plan_calls)}"
    )
    fix_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]
    assert not fix_calls, (
        "apply_qa_fixes must NOT run on the rescope (fix-forward) path"
    )


def test_triage_rescope_budget_bounds_dev_reentry(story_sandbox, monkeypatch):
    """triage_qa always asks to `rescope` and qa always fails → the dev<->qa loop is bounded.

    guard_triage caps rescopes at max_triage_scopes (2): plan re-runs exactly 1 + 2 = 3 times,
    after which the budget-spent guard forces the in-AC fix path; once that is also exhausted
    the run terminates (does NOT spin forever)."""
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["failed"])
    wf.mock_agent("triage_qa", {"triage_action": "rescope", "qa_failure_class": "code"})
    wf.mock_agent(
        "apply_qa_fixes", {"qa_result": {"status": "failed", "notes": "Still failing."}}
    )

    result = wf.run(params=story_params(story_sandbox))

    assert not result.passed(), (
        "Expected the run to terminate as failed, not loop forever"
    )
    plan_calls = [c for c in result.calls("claude") if c["node_id"] == "plan"]
    assert len(plan_calls) == 3, (
        f"plan should run 1 + max_triage_scopes(2) = 3 times, got {len(plan_calls)}"
    )
    # Once the rescope budget is spent, the guard forces the in-AC fix loop, which is itself
    # bounded by max_qa_reworks (3) before exhausting.
    fix_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]
    assert len(fix_calls) == 3, (
        f"in-AC fix loop should run max_qa_reworks=3 times, got {len(fix_calls)}"
    )


def test_qa_blocked_setup_fix_exhausted_escalates_to_operator(story_sandbox, monkeypatch):
    """qa stays blocked even after setup_fix → after max_setup_reworks (2) attempts → operator gate.

    setup_fix is bounded: it does not spin forever on a stack it cannot bring up. In human operator
    mode the escalation blocks at await_operator_qa.
    """
    git_mock_no_remote(story_sandbox)
    wf = WorkflowRun(WORKFLOW, story_sandbox)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )
    mock_qa_control_plane(wf, monkeypatch, ["blocked"])
    wf.mock_agent(
        "setup_fix",
        {"setup_result": {"status": "ready", "notes": "Attempted to start the stack."}},
    )

    result = wf.run(
        params={**story_params(story_sandbox), "operator_mode": "human"},
        timeout=OPERATOR_BLOCK_TIMEOUT,
    )

    assert result.exit_code == -1, "Expected the run to block at the operator gate"
    setup_calls = [c for c in result.calls("claude") if c["node_id"] == "setup_fix"]
    assert len(setup_calls) >= 1, "setup_fix should run before escalating"
