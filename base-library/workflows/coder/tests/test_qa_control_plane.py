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
    assert nodes["plan_qa"].next == "stamp_specs_qa_plan"
    assert nodes["stamp_specs_qa_plan"].next == "validate_qa_plan"
    assert nodes["validate_qa_plan"].next == "decide_qa_plan_validation"
    assert nodes["decide_qa_plan_validation"].cases["passed"] == "run_qa_plan"
    assert nodes["decide_qa_plan_validation"].cases["invalid"] == "guard_qa_plan"
    assert nodes["run_qa_plan"].next == "qa_interpret_and_explore"
    assert nodes["decide_qa_interpretation"].cases["continue"] == "decide_qa_run"
    assert nodes["decide_qa_run"].cases["passed"] == "verify_qa_evidence"
    assert nodes["decide_qa_evidence"].cases["passed"] == "audit_qa"

    assert graph.nodes["review"].next == "detect_okf"
    assert graph.nodes["decide_okf"].cases["yes"] == "document_story"
    assert graph.nodes["document_story"].next == "qa_phase"


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
    assert "interpreter, not the primary" in prompt
    assert "Do not:" in prompt
    assert "write or edit `qa-evidence.json`" in prompt
    assert "append replayable scenarios" in prompt
