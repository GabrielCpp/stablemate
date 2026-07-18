"""Structural tests for the Ostler QA control-plane topology and routing."""

from __future__ import annotations

from workhorse.graph.loader import load_workflow

from conftest import WORKFLOW


def test_primary_qa_topology_and_grounding_order() -> None:
    graph = load_workflow(WORKFLOW)
    nodes = graph.flows["qa"].nodes

    assert nodes["prepare_story"].next == "decide_qa_story"
    assert nodes["decide_qa_story"].default == "clear_qa_evidence"
    assert nodes["clear_qa_evidence"].next == "resolve_qa_context"
    assert nodes["resolve_qa_context"].next == "detect_qa_okf"
    assert nodes["detect_qa_okf"].next == "build_qa_okf_context"
    assert nodes["build_qa_okf_context"].next == "validate_qa_okf_context"
    assert nodes["decide_qa_okf_context"].cases["passed"] == "plan_qa"
    # The plan is stamped with its typed specs before it is validated: validate_qa_plan
    # checks a plan that already carries them, so the stamp cannot come after.
    assert nodes["plan_qa"].next == "clear_qa_gate_state"
    assert nodes["clear_qa_gate_state"].next == "stamp_specs_qa_plan"
    assert nodes["stamp_specs_qa_plan"].next == "validate_qa_plan"
    assert nodes["validate_qa_plan"].next == "decide_qa_plan_validation"
    assert nodes["decide_qa_plan_validation"].cases["passed"] == "review_qa_plan"
    assert nodes["decide_qa_plan_validation"].cases["invalid"] == "guard_qa_plan"
    assert nodes["review_qa_plan"].next == "decide_qa_plan_review"
    assert nodes["decide_qa_plan_review"].cases["approved"] == "run_qa_plan"
    assert nodes["decide_qa_plan_review"].cases["revise"] == "guard_qa_plan"
    assert nodes["run_qa_plan"].next == "assess_qa_run"
    assert nodes["decide_qa_assessment"].cases["confirmed"] == "decide_qa_assessment_runner_status"
    assert nodes["decide_qa_assessment"].cases["repair_plan"] == "guard_qa_plan"
    assert nodes["decide_qa_assessment"].cases["extend_plan"] == "guard_qa_plan"
    assert nodes["decide_qa_assessment"].cases["repair_setup"] == "guard_setup"
    assert nodes["decide_qa_assessment_runner_status"].cases["passed"] == "decide_qa_assessment_class"
    assert nodes["decide_qa_assessment_runner_status"].cases["failed"] == "decide_qa_assessment_class"
    assert nodes["decide_qa_assessment_runner_status"].cases["blocked"] == "guard_setup"
    assert nodes["decide_qa_assessment_runner_status"].cases["invalid"] == "guard_qa_plan"
    assert nodes["decide_qa_assessment_class"].cases["none"] == "decide_qa_assessment_objective"
    assert nodes["decide_qa_assessment_class"].cases["product"] == "mark_qa_assessment_failed"
    assert nodes["decide_qa_assessment_class"].cases["plan"] == "guard_qa_plan"
    assert nodes["decide_qa_assessment_class"].cases["evidence"] == "guard_qa_plan"
    assert nodes["decide_qa_assessment_class"].cases["environment"] == "guard_setup"
    assert nodes["decide_qa_assessment_objective"].cases["yes"] == "decide_qa_run"
    assert nodes["decide_qa_assessment_objective"].cases["no"] == "guard_qa_plan"
    assert nodes["mark_qa_assessment_failed"].next == "file_backlog_items"
    assert nodes["decide_qa_run"].cases["passed"] == "verify_qa_evidence"
    assert nodes["decide_qa_evidence"].cases["passed"] == "audit_qa"
    assert nodes["audit_qa"].next == "decide_qa_audit"
    assert nodes["decide_qa_audit"].cases["stands"] == "decide_qa_audit_stand"
    assert nodes["decide_qa_audit"].cases["refuted"] == "decide_qa_audit_refutation"
    assert nodes["decide_qa_audit_stand"].cases["none"] == "file_backlog_items"
    assert nodes["decide_qa_audit_stand"].default == "guard_qa_plan"
    assert nodes["decide_qa_audit_refutation"].cases["plan-defect"] == "guard_qa_plan"
    assert nodes["decide_qa_audit_refutation"].cases["evidence-defect"] == "guard_qa_plan"
    assert (
        nodes["decide_qa_audit_refutation"].cases["product-contradiction"]
        == "mark_qa_audit_failed"
    )
    assert nodes["mark_qa_audit_failed"].next == "file_backlog_items"
    assert nodes["plan_qa"].args["plan_validation_notes"] == "{{ qa_plan_validation.notes }}"
    assert nodes["plan_qa"].args["plan_review_notes"] == "{{ qa_plan_review.notes }}"
    assert nodes["plan_qa"].args["run_assessment_notes"] == "{{ qa_assessment.notes }}"
    assert nodes["plan_qa"].args["audit_notes"] == "{{ qa_audit.notes }}"
    assert nodes["plan_qa"].args["evidence_notes"] == "{{ qa_result.notes }}"
    assert nodes["run_regression"].next == "decide_regression_run"
    assert nodes["decide_regression_run"].cases["passed"] == "decide_regression_fix_applied"
    assert nodes["decide_regression_run"].cases["blocked"] == "prepare_regression_setup_reqa"
    assert nodes["prepare_regression_setup_reqa"].next == "guard_setup"
    assert nodes["decide_regression_fix_applied"].cases["yes"] == "mark_regression_reqa_pending"
    assert nodes["decide_regression_reqa_pending"].cases["yes"] == "clear_regression_reqa_pending"
    assert nodes["mark_regression_reqa_pending"].next == "build_qa_okf_context"
    assert nodes["clear_regression_reqa_pending"].next == "flush_root_screenshots"
    assert nodes["guard_regression_fix"].default == "clear_regression_reqa_before_fix"
    assert nodes["clear_regression_reqa_before_fix"].next == "fix_regression"
    assert nodes["incr_regression_fix"].next == "mark_regression_fix_applied"
    assert nodes["mark_regression_fix_applied"].next == "run_regression"
    assert nodes["mark_regression_unresolved"].next == "clear_regression_state_unresolved"
    assert nodes["clear_regression_state_unresolved"].next == "guard_qa"
    assert "reset_regression_after_fix" not in nodes

    assert nodes["guard_qa_context"].path == "qa_context_rework_count.value"
    assert nodes["guard_qa_plan"].path == "qa_plan_rework_count.value"
    assert nodes["guard_qa"].path == "qa_rework_count.value"
    assert "qa_assessment.notes" in nodes["setup_fix"].args["qa_notes"]

    assert graph.nodes["review"].next == "docs"
    assert graph.nodes["docs"].name == "docs"
    assert graph.nodes["docs"].next == "decide_docs_outcome"
    assert graph.nodes["decide_docs_outcome"].cases["passed"] == "qa_phase"
    assert graph.nodes["decide_docs_outcome"].default == "documentation_failed"
    assert graph.nodes["decide_post_drain"].cases["story"] == "final_docs"
    assert graph.nodes["decide_post_drain"].cases["epic"] == "final_docs"
    assert graph.nodes["final_docs"].name == "docs"
    assert graph.nodes["final_docs"].next == "decide_final_docs_outcome"
    assert graph.nodes["decide_final_docs_outcome"].cases["passed"] == "decide_final_docs"
    assert graph.nodes["decide_final_docs_outcome"].default == "documentation_failed"
    assert graph.nodes["decide_final_docs"].cases["story"] == "commit_story_pr"
    assert graph.nodes["decide_final_docs"].cases["epic"] == "commit_story"
    assert graph.nodes["decide_qa_fail"].cases["epic"] == "failed_docs"
    assert graph.nodes["failed_docs"].next == "decide_failed_docs_outcome"
    assert graph.nodes["decide_failed_docs_outcome"].cases["passed"] == "qa_give_up"
    assert graph.nodes["decide_failed_docs_outcome"].default == "documentation_failed"
    assert graph.nodes["fix_ci"].next == "push_ci"
    assert graph.nodes["fix_merge"].next == "push_merge"
    assert getattr(graph.nodes["documentation_failed"], "type", None) == "fail"


def test_documentation_flow_is_hard_gated_and_fail_closed() -> None:
    graph = load_workflow(WORKFLOW)
    nodes = graph.flows["docs"].nodes

    assert nodes["prepare_story"].next == "decide_documentation_story"
    assert nodes["decide_documentation_story"].conditions[0].next == "documentation_failed"
    assert nodes["detect_documentation_okf"].next == "decide_documentation_okf"
    assert nodes["decide_documentation_okf"].cases["yes"] == "reset_documentation_rework"
    assert nodes["decide_documentation_okf"].cases["no"] == "mark_documentation_not_applicable"
    assert nodes["decide_documentation_okf"].cases["invalid"] == "documentation_failed"
    assert nodes["decide_documentation_okf"].default == "documentation_failed"
    assert nodes["document_story"].next == "decide_documentation_result"
    assert nodes["decide_documentation_result"].cases["blocked"] == "documentation_failed"
    assert nodes["reset_documentation_rework"].next == "classify_documentation_context"
    assert nodes["classify_documentation_context"].next == "document_story"
    assert nodes["decide_documentation_result"].cases["documented"] == "decide_documentation_context_mode"
    assert nodes["decide_documentation_context_mode"].cases["local"] == "build_documentation_context"
    assert nodes["decide_documentation_context_mode"].cases["semantic"] == "verify_story_documentation"
    assert nodes["build_documentation_context"].next == "validate_documentation_context"
    assert nodes["validate_documentation_context"].next == "verify_story_documentation"
    assert nodes["verify_story_documentation"].next == "decide_documentation_gate"
    assert nodes["decide_documentation_gate"].cases["passed"] == "review_story_documentation"
    assert nodes["decide_documentation_gate"].default == "guard_documentation"
    assert nodes["review_story_documentation"].next == "decide_documentation_review"
    assert nodes["decide_documentation_review"].cases["approved"] == "mark_documentation_passed"
    assert nodes["decide_documentation_review"].cases["blocked"] == "documentation_failed"
    assert nodes["guard_documentation"].conditions[0].next == "documentation_failed"
    assert nodes["guard_documentation"].default == "incr_documentation_rework"
    assert nodes["incr_documentation_rework"].next == "document_story"
    assert getattr(nodes["documentation_failed"], "type", None) == "fail"

    fix_nodes = graph.flows["fix"].nodes
    assert fix_nodes["prune_fix_item"].next == "document_fix_item"
    assert fix_nodes["fix_give_up"].next == "document_fix_item"
    assert fix_nodes["document_fix_item"].name == "docs"
    assert fix_nodes["document_fix_item"].next == "decide_fix_documentation"
    assert fix_nodes["decide_fix_documentation"].cases["passed"] == "commit_fix_item"
    assert fix_nodes["decide_fix_documentation"].default == "fix_documentation_failed"
    assert getattr(fix_nodes["fix_documentation_failed"], "type", None) == "fail"


def test_four_states_route_fail_closed_without_pass_defaults() -> None:
    graph = load_workflow(WORKFLOW)
    nodes = graph.flows["qa"].nodes
    routes = nodes["decide_qa_run"].cases

    assert routes["invalid"] == "guard_qa_plan"
    assert routes["blocked"] == "file_backlog_items"
    assert routes["failed"] == "file_backlog_items"
    assert routes["passed"] == "verify_qa_evidence"
    assert nodes["decide_qa"].cases["blocked"] == "guard_setup"
    assert nodes["decide_qa"].cases["failed"] == "triage_qa"
    assert nodes["decide_qa"].cases["invalid"] == "guard_qa_plan"
    assert graph.nodes["qa_phase"].outputs[0].default == "exhausted"


def test_qa_agent_prompt_has_no_primary_execution_or_manifest_authorship() -> None:
    prompt = (WORKFLOW.parent / "prompts" / "qa-story.md").read_text(encoding="utf-8")
    assert "constructive execution reviewer" in prompt
    assert "Do not:" in prompt
    assert "write or edit `qa-evidence.json`" in prompt
    assert "append only replayable" in prompt.lower()
    assert "qa-plan.md` as the planner's rationale" in prompt
    assert "docs/qa/lessons.md" in prompt


def test_auditor_is_pass_only_and_cannot_repair_or_execute() -> None:
    prompt = (WORKFLOW.parent / "prompts" / "audit-qa.md").read_text(encoding="utf-8")
    assert "as frozen and independently try to refute" in prompt
    assert "Do not execute the product, edit the" in prompt
    assert "The auditor never repairs or extends QA" in prompt
    assert '"qa_audit"' in prompt
