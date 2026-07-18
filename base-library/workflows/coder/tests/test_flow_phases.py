"""Tests for the composable per-story phases (`flows: dev / review / docs / qa`).

The per-story pipeline is factored into four `flows:` sub-graphs so any one phase
can be re-run STANDALONE against an already-built story without replaying the whole
pipeline — the re-QA-a-flagged-story workflow:

    workhorse run coder qa --params '{"story_path":…,"spec_dir":…,…}'

These tests drive each flow on its own (``WorkflowRun.run(flow=…)``) and assert it
runs to its terminal with the right phase-status, plus the structural invariants of
the split (flows present, the parent sequences them, the standalone param contract).
The composed path (a normal coder run threading dev→review→qa) is already covered by
test_story_mode.py / test_epic_mode.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from workhorse.graph.loader import load_workflow
from workhorse.testing import WorkflowRun, assert_step_output

from conftest import (
    WORKFLOW,
    _qa_cli_module,
    make_story,
    git_mock_no_remote,
    mock_documentation_happy,
    mock_ostler_qa,
    mock_qa_control_plane,
)


def _qa_params(sandbox: Path, epic: str = "epic-1", slug: str = "s-1") -> dict:
    """The `qa` flow's parameter contract: slug + docs root."""
    return {
        "story": slug,
        "docs_path": str(sandbox),
        "epic": epic,
    }


# ── Structure: the split is wired the way the parent expects ────────────────────


def test_workflow_declares_phase_and_standalone_flows():
    g = load_workflow(WORKFLOW)
    # dev/review/docs/qa are the per-story phases; fix_ci and dream are standalone flows.
    assert {"dev", "review", "docs", "qa"} <= set(g.flows)
    # Each phase flow's vars ARE its standalone parameter contract (slug + docs root).
    assert set(g.flows["dev"].vars) >= {"story", "docs_path", "epic"}
    assert set(g.flows["docs"].vars) >= {"story", "docs_path", "epic"}
    assert set(g.flows["qa"].vars) >= {"story", "docs_path", "epic"}
    # The parent sequences the four phases via `type: flow` nodes (dream is NOT inline —
    # it's offline consolidation, never sequenced into the per-story build pipeline).
    flow_nodes = {
        nid: n for nid, n in g.nodes.items() if getattr(n, "type", None) == "flow"
    }
    phase_names = {n.name for n in flow_nodes.values()}
    assert {"dev", "review", "docs", "qa"} <= phase_names
    assert "dream" not in phase_names


def test_dream_is_a_standalone_offline_reflection_flow():
    """`dream` is a standalone flow (workhorse run coder dream) that reflects on a run's
    PROCESS record and drains proposals to a durable ledger — NOT inline in the build
    pipeline (so it never slows or gates a story), and never mutating the workflow."""
    g = load_workflow(WORKFLOW)
    # Not inline: qa_phase goes straight to the QA outcome branch, no reflection node.
    assert g.nodes["qa_phase"].next == "decide_qa_outcome"
    assert "self_reflect" not in g.nodes
    # The dream flow exists with its three-stage shape: gather → reflect → record.
    assert "dream" in g.flows
    d = g.flows["dream"].nodes
    assert set(g.flows["dream"].vars) >= {"run_dir", "docs_path"}
    assert d["gather_run_evidence"].script == "scripts/gather-run-evidence.py"
    assert d["gather_run_evidence"].next == "dream_reflect"
    assert d["dream_reflect"].prompt == "prompts/dream-reflect.md"
    assert d["dream_reflect"].next == "record_improvements"
    assert d["record_improvements"].script == "scripts/record-improvements.py"
    assert d["record_improvements"].next == "dream_done"
    assert getattr(d["dream_done"], "type", None) == "terminal"


# ── Standalone `qa` — the re-QA entrypoint ──────────────────────────────────────


def test_standalone_qa_passes(tmp_path, monkeypatch):
    """`workhorse run coder qa` on a built story: plan_qa → qa → audit → green → passed."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_qa_control_plane(wf, monkeypatch)
    wf.mock_agent(
        "audit_qa", {"qa_audit": {"verdict": "stands", "refutation_class": "none", "notes": "Audit upheld."}}
    )

    result = wf.run(flow="qa", params=_qa_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    # The flow ran to its passed terminal (mark_qa_passed stamps the phase status).
    assert_step_output(result, "mark_qa_passed", "qa_status", "passed")
    # No parent machinery ran — this is a standalone phase run, not the full pipeline.
    assert result.step_outputs("commit_story") == {}


def test_standalone_qa_exhausted_returns_status_not_halt(tmp_path, monkeypatch):
    """Standalone qa that never passes runs to its terminal with qa_status=exhausted
    (exit 0) — it returns the outcome for the operator to act on rather than halting;
    the per-mode fail routing is the PARENT's job (decide_qa_fail)."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_qa_control_plane(wf, monkeypatch, statuses=["failed"])
    wf.mock_agent(
        "apply_qa_fixes", {"qa_result": {"status": "failed", "notes": "Still failing."}}
    )

    result = wf.run(flow="qa", params=_qa_params(tmp_path))

    assert result.passed(), f"a standalone phase returns, not halts\n{result.stderr}"
    assert_step_output(result, "mark_qa_exhausted", "qa_status", "exhausted")
    fix_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_qa_fixes"]
    assert len(fix_calls) == 3, f"bounded to max_qa_reworks=3, got {len(fix_calls)}"


def test_standalone_qa_no_story_slug_prepare_story_returns_empty(tmp_path):
    """Running the qa flow with no `story` slug runs prepare_story which emits empty paths,
    then clear_qa_evidence and resolve_qa_context are no-ops, and the run proceeds to plan_qa
    which gets a blank story_path and should report it (not crash the runner)."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    # Running with an empty story slug should not crash — prepare_story exits with empty outputs.
    result = wf.run(
        flow="qa", params={"docs_path": str(tmp_path), "story": "", "epic": "epic-1"}
    )
    assert result.passed() or result.exit_code == 2


# ── Standalone `dev` and `review` — the other re-run entrypoints ────────────────


def test_standalone_dev_plan_and_implement(tmp_path):
    """`workhorse run coder dev`: plan (done) → implement → ready terminal."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})

    result = wf.run(flow="dev", params=_qa_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(
        result, "implement_layer", "impl_result", {"status": "done", "notes": ""}
    )


def test_standalone_review_runs_to_approved(tmp_path):
    """`workhorse run coder review`: review_implementation (approved) → review_done."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "approved", "notes": ""}},
    )

    result = wf.run(
        flow="review",
        params={"story": "s-1", "docs_path": str(tmp_path), "epic": "epic-1"},
    )

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(
        result,
        "review_implementation",
        "review_impl_result",
        {"status": "approved", "notes": ""},
    )


def test_standalone_docs_gates_epics_bundle_before_first_feature(tmp_path, monkeypatch):
    """An epics-only OKF bundle must scaffold/gate its first feature, not bypass docs."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_ostler_qa(monkeypatch)
    mock_documentation_happy(wf)

    result = wf.run(flow="docs", params=_qa_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "mark_documentation_passed", "doc_status", "passed")
    assert [c for c in result.calls("claude") if c["node_id"] == "document_story"]


def test_standalone_docs_passes_author_review_and_deterministic_gate(tmp_path, monkeypatch):
    """An OKF workspace must clear authoring, context, doctor, and semantic review."""
    from ostler import Ostler

    make_story(tmp_path, "epic-1", "s-1", "In progress")
    feature = tmp_path / "docs/features/acme/concepts/example.md"
    feature.parent.mkdir(parents=True)
    feature.write_text(
        "---\ntype: concept\ntitle: Example\n---\n# Example\n\n- code: `src/example.py::Example`\n",
        encoding="utf-8",
    )
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_ostler_qa(monkeypatch)
    monkeypatch.setattr(Ostler, "doctor", lambda self: {"findings": []})

    packet = {
        "version": 1,
        "available": True,
        "changedCode": [],
        "directNodes": [],
        "obligations": [],
        "healthFindings": [],
    }

    def qa_context(spec_dir, **_kwargs):
        path = Path(spec_dir)
        if not path.is_absolute():
            path = tmp_path / path
        path.mkdir(parents=True, exist_ok=True)
        (path / "qa-okf-context.json").write_text(
            json.dumps(packet), encoding="utf-8"
        )
        return 0, packet, ""

    qa_cli = _qa_cli_module()
    monkeypatch.setattr(qa_cli, "qa_context", qa_context)
    monkeypatch.setattr(
        qa_cli,
        "qa_context_validate",
        lambda *args, **kwargs: (0, {"status": "passed", "problems": []}, ""),
    )
    wf.mock_agent(
        "document_story",
        {
            "documentation_result": {
                "status": "documented",
                "nodes": ["docs/features/acme/concepts/example.md"],
                "notes": "Current contracts updated.",
            }
        },
    )
    wf.mock_agent(
        "review_story_documentation",
        {
            "documentation_review": {
                "status": "approved",
                "notes": "Complete current book.",
            }
        },
    )

    result = wf.run(flow="docs", params=_qa_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert_step_output(result, "mark_documentation_passed", "doc_status", "passed")
    calls = [c["node_id"] for c in result.calls("claude")]
    assert calls == ["document_story", "review_story_documentation"]


# ── Review remediation loop is BOUNDED (the 03b-editor-visual-fidelity incident) ──
# Before this, review_implementation<->apply_review had no counter (unlike every
# sibling loop), so an unsatisfiable review finding spun it forever. These assert the
# containment backstop: a counter+guard caps the loop at max_review_reworks and
# escalates to the operator, and an apply_review `blocked` short-circuits to the gate.


def test_review_loop_structure_is_bounded():
    """Pure-graph check (no scripts): the review loop has the init/incr/guard counter
    triple every other bounded loop has, honors apply_review's `blocked`, and routes
    exhaustion to an operator gate."""
    g = load_workflow(WORKFLOW)
    nodes = g.flows["review"].nodes  # id -> node

    # The counter is seeded on entry and bumped each apply pass.
    assert nodes["reset_review"].fn == "seed"
    assert nodes["incr_review"].fn == "incr"

    # decide_impl no longer dead-ends into an unbounded apply_review — it gates first.
    assert nodes["decide_impl"].cases["needs_changes"] == "guard_review"
    assert nodes["decide_impl"].default == "guard_review"

    # guard_review caps the loop at max_review_reworks (literal "3") → operator gate.
    guard = nodes["guard_review"]
    assert guard.path == "review_rework_count.value"
    assert guard.default == "apply_review"
    exhaust = [c for c in guard.conditions if c.op == ">=" and c.value == "3"]
    assert exhaust and exhaust[0].next == "gate_review"

    # apply_review's verdict runs through the deterministic, fail-closed resolution gate
    # (ostler settle-review) BEFORE decide_apply_review branches — so the loop trusts a
    # verified PER-FINDING settlement, not the agent's self-attestation.
    assert nodes["apply_review"].next == "verify_review_resolution"
    assert (
        nodes["verify_review_resolution"].script
        == "scripts/verify-review-resolution.py"
    )
    assert nodes["verify_review_resolution"].next == "decide_apply_review"
    dec = nodes["decide_apply_review"]
    assert dec.path == "impl_result.status"
    # 4.3 granularity: every finding verified → approve & EXIT (no full re-review that
    # would re-litigate already-settled findings); a blocked finding escalates by itself.
    assert dec.cases["applied"] == "check_impl_feedback"
    assert dec.cases["blocked"] == "gate_review"  # honest blocked → operator
    assert dec.default == "incr_review"  # findings still open → re-apply only those
    # The re-apply is TARGETED: it goes back through guard_review (still bounded), NOT a
    # fresh review_implementation — that is the goalpost-moving full re-review 4.3 kills.
    assert nodes["incr_review"].next == "guard_review"

    # The operator gate mirrors gate_qa/gate_plan; a resolved block re-seeds the budget.
    assert set(nodes["gate_review"].cases.values()) == {
        "await_operator_review",
        "resolve_review",
    }
    assert nodes["apply_review_resolved"].next == "reset_review"


def test_review_loop_caps_at_max_reworks_then_escalates(tmp_path, monkeypatch):
    """An apply_review whose findings never settle (status stays needs_changes — proof
    missing/wrong) re-applies at most max_review_reworks=3 times, then escalates to the
    operator gate (human mode → await_operator_review halts) instead of looping forever.
    review_implementation runs ONCE; the bounded loop is now apply→settle→re-apply."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_ostler_qa(monkeypatch)
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "needs_changes", "notes": "still wrong"}},
    )
    # No review-resolution.json in the sandbox → verify_review_resolution passes this
    # status through; never "applied", so the loop re-applies until the cap.
    wf.mock_agent(
        "apply_review",
        {"impl_result": {"status": "needs_changes", "notes": "still open"}},
    )

    result = wf.run(
        flow="review",
        params={
            "story": "s-1",
            "docs_path": str(tmp_path),
            "epic": "epic-1",
            "operator_mode": "human",
        },
        timeout=20,
    )

    # await_operator_review writes context.md and HALTS (non-zero exit) — the intended
    # "needs human" signal, exactly like the plan/QA operator gates.
    assert not result.passed(), (
        "exhausted review must escalate (halt), not loop forever"
    )
    apply_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_review"]
    assert len(apply_calls) == 3, (
        f"bounded to max_review_reworks=3, got {len(apply_calls)}"
    )
    # The full re-review does NOT re-run each pass — it ran once to emit the findings.
    review_calls = [
        c for c in result.calls("claude") if c["node_id"] == "review_implementation"
    ]
    assert len(review_calls) == 1, (
        f"review_implementation runs once, got {len(review_calls)}"
    )


def test_review_apply_settles_then_approves_without_full_rereview(tmp_path, monkeypatch):
    """The 4.3 happy path: review finds changes, apply settles them (status `applied`),
    and the loop APPROVES and exits — it does NOT re-run review_implementation a second
    time to re-litigate the now-settled findings."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_ostler_qa(monkeypatch)
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "needs_changes", "notes": "fix the label"}},
    )
    wf.mock_agent(
        "apply_review", {"impl_result": {"status": "applied", "notes": "fixed + proof"}}
    )

    result = wf.run(
        flow="review",
        params={
            "story": "s-1",
            "docs_path": str(tmp_path),
            "epic": "epic-1",
            "operator_mode": "human",
        },
        timeout=20,
    )

    assert result.passed(), f"settled review should reach review_done\n{result.stderr}"
    apply_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_review"]
    review_calls = [
        c for c in result.calls("claude") if c["node_id"] == "review_implementation"
    ]
    assert len(apply_calls) == 1, f"one apply pass settled it, got {len(apply_calls)}"
    assert len(review_calls) == 1, (
        f"no goalpost-moving re-review, got {len(review_calls)}"
    )


def test_review_blocked_apply_escalates_immediately(tmp_path, monkeypatch):
    """An apply_review that reports `blocked` (a finding it cannot resolve) escalates to
    the operator at once rather than re-reviewing and spinning."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_ostler_qa(monkeypatch)
    wf.mock_agent(
        "review_implementation",
        {
            "review_impl_result": {
                "status": "needs_changes",
                "notes": "product decision needed",
            }
        },
    )
    wf.mock_agent(
        "apply_review",
        {"impl_result": {"status": "blocked", "notes": "needs a product decision"}},
    )

    result = wf.run(
        flow="review",
        params={
            "story": "s-1",
            "docs_path": str(tmp_path),
            "epic": "epic-1",
            "operator_mode": "human",
        },
        timeout=20,
    )

    assert not result.passed(), "a blocked remediation must escalate (halt), not loop"
    apply_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_review"]
    assert len(apply_calls) == 1, (
        f"blocked short-circuits after one apply pass, got {len(apply_calls)}"
    )


# ── Code-reuse gates (anti-reimplementation) ────────────────────────────────────
# Two new stages added to mitigate the workflow rebuilding features/utilities that
# already exist: a DEV-stage plan-level check (check_code_reuse) that reworks the plan
# before any code is written, and a REVIEW-stage pass (code_reuse) whose findings feed
# the implementation reviewer's verdict so duplication drives the existing rework loop.


def test_dev_code_reuse_gate_structure_is_bounded():
    """Pure-graph check: the dev flow routes an approved plan through the reuse gate,
    which reworks the plan on `needs_rework` and is bounded by max_reuse_reworks."""
    g = load_workflow(WORKFLOW)
    nodes = g.flows["dev"].nodes

    # An approved plan flows into the reuse gate (not straight to validate_plan).
    assert nodes["decide_plan"].cases["done"] == "seed_reuse"
    assert nodes["decide_plan"].default == "seed_reuse"
    # blocked still escalates to the operator gate — the reuse gate never sees it.
    assert nodes["decide_plan"].cases["blocked"] == "gate_plan"

    # seed → check → decide, with the init/incr/guard counter triple of a bounded loop.
    assert nodes["seed_reuse"].fn == "seed"
    assert nodes["seed_reuse"].next == "check_code_reuse"
    assert nodes["check_code_reuse"].prompt == "prompts/check-code-reuse.md"
    assert nodes["check_code_reuse"].next == "decide_reuse"

    dec = nodes["decide_reuse"]
    assert dec.path == "reuse_result.status"
    assert dec.cases["ok"] == "validate_plan"   # clean → implementation
    assert dec.cases["needs_rework"] == "guard_reuse"
    assert dec.default == "validate_plan"        # fail-open

    # guard caps the loop at max_reuse_reworks (literal "2") → proceed to validate_plan.
    guard = nodes["guard_reuse"]
    assert guard.path == "reuse_rework_count.value"
    assert guard.default == "rework_plan_reuse"
    exhaust = [c for c in guard.conditions if c.op == ">=" and c.value == "2"]
    assert exhaust and exhaust[0].next == "validate_plan"

    # rework reuses the refine-plan prompt, then bumps the counter and re-checks.
    assert nodes["rework_plan_reuse"].prompt == "prompts/refine-plan.md"
    assert nodes["rework_plan_reuse"].next == "incr_reuse"
    assert nodes["incr_reuse"].fn == "incr"
    assert nodes["incr_reuse"].next == "check_code_reuse"


def test_dev_code_reuse_reworks_plan_then_proceeds(tmp_path):
    """check_code_reuse finds a re-implementation once → the plan is reworked → the
    re-check comes back clean → implementation proceeds."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent_sequence(
        "check_code_reuse",
        [
            {"reuse_result": {"status": "needs_rework",
                              "findings": [{"intended": "email validator",
                                            "existing": "pkg/validate/email.go",
                                            "recommendation": "call it"}],
                              "summary": "reuse the existing validator"}},
            {"reuse_result": {"status": "ok", "findings": [], "summary": ""}},
        ],
    )
    wf.mock_agent(
        "rework_plan_reuse", {"plan_result": {"status": "done", "summary": "reuse"}}
    )
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})

    result = wf.run(flow="dev", params=_qa_params(tmp_path))

    assert result.passed(), f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    rework = [c for c in result.calls("claude") if c["node_id"] == "rework_plan_reuse"]
    check = [c for c in result.calls("claude") if c["node_id"] == "check_code_reuse"]
    assert len(rework) == 1, f"one rework pass, got {len(rework)}"
    assert len(check) == 2, f"check runs, reworks, re-checks, got {len(check)}"
    assert_step_output(
        result, "implement_layer", "impl_result", {"status": "done", "notes": ""}
    )


def test_dev_code_reuse_loop_is_bounded_then_proceeds(tmp_path):
    """A check that NEVER comes back clean reworks the plan at most max_reuse_reworks=2
    times, then proceeds to implementation anyway (fail-open advisory gate — it must not
    spin or halt the run; review/QA re-check reuse on the real diff)."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": ""}})
    wf.mock_agent(
        "check_code_reuse",
        {"reuse_result": {"status": "needs_rework", "findings": [], "summary": "again"}},
    )
    wf.mock_agent(
        "rework_plan_reuse", {"plan_result": {"status": "done", "summary": "reuse"}}
    )
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})

    result = wf.run(flow="dev", params=_qa_params(tmp_path), timeout=20)

    assert result.passed(), "advisory reuse gate must proceed, not halt"
    rework = [c for c in result.calls("claude") if c["node_id"] == "rework_plan_reuse"]
    assert len(rework) == 2, f"bounded to max_reuse_reworks=2, got {len(rework)}"
    assert_step_output(
        result, "implement_layer", "impl_result", {"status": "done", "notes": ""}
    )


def test_review_code_reuse_stage_wired_and_feeds_reviewer():
    """The review flow runs the dedicated code-reuse stage between the automated code
    review and the implementation reviewer, and passes its result into the reviewer."""
    g = load_workflow(WORKFLOW)
    nodes = g.flows["review"].nodes
    assert nodes["code_review"].next == "code_reuse"
    assert nodes["code_reuse"].prompt == "prompts/code-reuse.md"
    assert nodes["code_reuse"].next == "review_implementation"
    # Fail-open default so a defaulted stage never blocks the reviewer.
    reuse_out = {o.key: o for o in nodes["code_reuse"].outputs}
    assert reuse_out["code_reuse_result"].default["status"] == "skipped"
    # The reviewer consumes both automated sources.
    assert "code_reuse_result" in nodes["review_implementation"].args


def test_review_code_reuse_findings_drive_rework(tmp_path, monkeypatch):
    """A code-reuse finding the reviewer folds into a needs_changes verdict drives the
    existing apply_review rework loop; the code-reuse stage runs once per review entry."""
    make_story(tmp_path, "epic-1", "s-1", "In progress")
    wf = WorkflowRun(WORKFLOW, tmp_path)
    git_mock_no_remote(tmp_path)
    mock_ostler_qa(monkeypatch)
    wf.mock_agent(
        "code_reuse",
        {"code_reuse_result": {"status": "findings",
                               "findings": [{"repo": "api-service", "file": "x.go",
                                             "line": 1, "category": "Missed Utility",
                                             "severity": "Major", "issue": "reinvents util.Ptr",
                                             "required_fix": "use util.Ptr"}],
                               "findings_summary": "1 missed utility"}},
    )
    wf.mock_agent(
        "review_implementation",
        {"review_impl_result": {"status": "needs_changes", "notes": "use util.Ptr"}},
    )
    wf.mock_agent(
        "apply_review", {"impl_result": {"status": "applied", "notes": "fixed"}}
    )

    result = wf.run(
        flow="review",
        params={"story": "s-1", "docs_path": str(tmp_path), "epic": "epic-1",
                "operator_mode": "human"},
        timeout=20,
    )

    assert result.passed(), f"settled reuse rework should approve\n{result.stderr}"
    reuse = [c for c in result.calls("claude") if c["node_id"] == "code_reuse"]
    apply_calls = [c for c in result.calls("claude") if c["node_id"] == "apply_review"]
    assert len(reuse) == 1, f"code_reuse runs once per review entry, got {len(reuse)}"
    assert len(apply_calls) == 1, f"the finding drove one apply pass, got {len(apply_calls)}"
