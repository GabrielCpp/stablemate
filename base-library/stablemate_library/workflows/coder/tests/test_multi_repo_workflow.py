"""Integration tests for multi-repo workflow nodes.

Tests the layer iteration loop (select_impl_layer → decide_impl_layer → implement_layer)
using the WorkflowRun harness against a real tmp_path sandbox with a fully valid
workspace and plan-context so that the validate_plan script passes cleanly.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from conftest import WORKFLOW, make_story, git_mock_no_remote, mock_ostler_qa, story_params
from workhorse.testing import WorkflowRun


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_plan_context(spec_dir: Path, services: list[dict]) -> None:
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "plan-context.json").write_text(
        json.dumps({
            "services": services,
            "implementation_order": [f"{s['repo']}::{s['path']}" for s in services],
        }, indent=2),
        encoding="utf-8",
    )


def _seed_service(sandbox: Path, repo_name: str, svc_path: str, marker: str = "main.go") -> None:
    """Create a service directory with an agents.yml and marker file."""
    repo = sandbox / repo_name
    svc = repo / svc_path
    svc.mkdir(parents=True)
    (svc / marker).write_text("package main", encoding="utf-8")
    (repo / "agents.yml").write_text(
        yaml.dump({
            "repo": {"name": repo_name},
            "workspace": {
                "service_markers": ["main.go", "package.json"],
                "qa_mode": "cli",
                "verification": "go build ./...",
            },
        }),
        encoding="utf-8",
    )


def _seed_workspace_file(sandbox: Path, repo_names: list[str]) -> Path:
    folders = [{"name": n, "path": n} for n in repo_names]
    ws_file = sandbox / "workspace.code-workspace"
    ws_file.write_text(json.dumps({"folders": folders}, indent=2), encoding="utf-8")
    return ws_file


def _seed_valid_plan(sandbox: Path, spec_dir_rel: str, services: list[dict]) -> None:
    """Seed plan-context.json with valid services (paths that actually exist)."""
    spec_dir = sandbox / spec_dir_rel
    _seed_plan_context(spec_dir, services)
    for svc in services:
        plan_file = svc.get("plan_file", "plan.md")
        (spec_dir / plan_file).write_text(f"# Plan for {svc['path']}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Layer loop iterates all services
# ---------------------------------------------------------------------------


def test_layer_loop_iterates_all_services(tmp_path, monkeypatch):
    """A 2-service story → implement_layer is called twice with correct CWDs."""
    make_story(tmp_path, "epic-1", "s-1")
    spec_dir_rel = "docs/specs/s-1"

    _seed_service(tmp_path, "api-service", "cmd/alert")
    _seed_service(tmp_path, "web-app", "packages/discover", marker="package.json")
    ws_file = _seed_workspace_file(tmp_path, ["api-service", "web-app"])
    _seed_valid_plan(tmp_path, spec_dir_rel, [
        {"repo": "api-service", "path": "cmd/alert", "type": "go", "plan_file": "plan-alert.md", "skills": []},
        {"repo": "web-app", "path": "packages/discover", "type": "svelte", "plan_file": "plan-discover.md", "skills": []},
    ])
    git_mock_no_remote(tmp_path)

    wf = WorkflowRun(WORKFLOW, tmp_path)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": "Plan written."}})
    wf.mock_agent("rework_plan", {"plan_result": {"status": "done", "summary": "Reworked."}})
    wf.mock_agent("rework_plan_paths", {"plan_result": {"status": "done", "summary": "Paths fixed."}})
    # implement_layer called once per service
    wf.mock_agent_sequence("implement_layer", [
        {"impl_result": {"status": "done", "notes": "api-service done"}},
        {"impl_result": {"status": "done", "notes": "web-app done"}},
    ])
    wf.mock_agent("review_implementation", {"review_impl_result": {"status": "approved", "notes": ""}})
    wf.mock_agent("apply_review", {"impl_result": {"status": "applied", "notes": ""}})
    wf.mock_agent("plan_qa", {"qa_plan_result": {"status": "done", "notes": ""}})
    wf.mock_agent("audit_qa", {"qa_result": {"status": "passed", "notes": ""}})
    wf.mock_agent("qa", {"qa_result": {"status": "passed", "notes": ""}})
    wf.mock_agent("fix_ci_agent", {"fix_ci_result": {"status": "fixed", "notes": ""}})

    result = wf.run(
        flow="dev",
        params=story_params(tmp_path),
        extra_env={
            "CODER_WORKSPACE": str(ws_file),
        },
    )

    # Both layers were dispatched — resolve_impl_context sets dispatch_count
    assert result.passed(), result.stderr
    assert result.step_outputs("resolve_impl_context").get("dispatch_count") == "2"


# ---------------------------------------------------------------------------
# 2. Single-service regression (mono-repo, no workspace file)
# ---------------------------------------------------------------------------


def test_validate_loop_is_bounded(tmp_path, monkeypatch):
    """A plan-context that never validates must not spin forever: the
    rework_plan_paths<->validate_plan loop is capped at max_validate_reworks (3) by
    guard_validate, then escalates to the operator gate. Proven by incr_plan_rework's
    final counter == 3 (exactly the bound) and the run not dying of gas exhaustion."""
    make_story(tmp_path, "epic-1", "s-1")
    spec_dir_rel = "docs/specs/s-1"

    # Seed a plan-context whose service path does NOT exist on disk → validate_plan
    # returns invalid every pass, and the (mocked) refine agent never fixes it.
    _seed_service(tmp_path, "api-service", "cmd/alert")
    ws_file = _seed_workspace_file(tmp_path, ["api-service"])
    _seed_plan_context(tmp_path / spec_dir_rel, [
        {"repo": "api-service", "path": "cmd/DOES_NOT_EXIST", "type": "go", "plan_file": "plan.md", "skills": []},
    ])
    (tmp_path / spec_dir_rel / "plan.md").write_text("# Plan\n", encoding="utf-8")

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    mock_ostler_qa(monkeypatch)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": "Plan written."}})
    # refine claims success but does NOT touch the bad path → stays invalid forever
    wf.mock_agent("rework_plan_paths", {"plan_result": {"status": "done", "summary": "Paths fixed."}})
    # escalation target in human mode halts (no operator answer) → run terminates

    result = wf.run(
        flow="dev",
        params={**story_params(tmp_path), "operator_mode": "human"},
        extra_env={"CODER_WORKSPACE": str(ws_file)},
        timeout=20,
    )

    # The loop ran exactly max_validate_reworks times, then the guard escalated —
    # not the gas-tank safety net (which would leave a much larger count / loop error).
    assert result.step_outputs("incr_plan_rework").get("plan_rework_count", {}).get("value") == 3
    assert "ran dry" not in result.stderr and "gas" not in result.stderr.lower(), result.stderr


def test_single_service_no_workspace_file(tmp_path):
    """Single-service story with no workspace file falls back to CWD-only mode."""
    make_story(tmp_path, "epic-1", "s-1")
    spec_dir_rel = "docs/specs/s-1"

    # Seed service in tmp_path itself (CWD = single-folder workspace)
    svc = tmp_path / "cmd" / "svc"
    svc.mkdir(parents=True)
    (svc / "main.go").write_text("package main", encoding="utf-8")
    (tmp_path / "agents.yml").write_text(
        yaml.dump({
            "repo": {"name": "myrepo"},
            "workspace": {"service_markers": ["main.go"]},
        }),
        encoding="utf-8",
    )

    _seed_valid_plan(tmp_path, spec_dir_rel, [
        {"repo": "myrepo", "path": "cmd/svc", "type": "go", "plan_file": "plan.md", "skills": []},
    ])

    git_mock_no_remote(tmp_path)
    wf = WorkflowRun(WORKFLOW, tmp_path)
    wf.mock_agent("plan", {"plan_result": {"status": "done", "summary": "Plan written."}})
    wf.mock_agent("rework_plan", {"plan_result": {"status": "done", "summary": "Reworked."}})
    wf.mock_agent("rework_plan_paths", {"plan_result": {"status": "done", "summary": "Paths fixed."}})
    wf.mock_agent("implement_layer", {"impl_result": {"status": "done", "notes": ""}})
    wf.mock_agent("review_implementation", {"review_impl_result": {"status": "approved", "notes": ""}})
    wf.mock_agent("apply_review", {"impl_result": {"status": "applied", "notes": ""}})
    wf.mock_agent("plan_qa", {"qa_plan_result": {"status": "done", "notes": ""}})
    wf.mock_agent("audit_qa", {"qa_result": {"status": "passed", "notes": ""}})
    wf.mock_agent("qa", {"qa_result": {"status": "passed", "notes": ""}})
    wf.mock_agent("fix_ci_agent", {"fix_ci_result": {"status": "fixed", "notes": ""}})

    result = wf.run(
        flow="dev",
        params=story_params(tmp_path),
        # No CODER_WORKSPACE → CWD-only fallback
    )

    # Single service resolved and dispatched
    assert result.passed(), result.stderr
    assert result.step_outputs("resolve_impl_context").get("dispatch_count") == "1"
