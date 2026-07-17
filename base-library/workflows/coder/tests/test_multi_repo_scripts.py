"""Direct subprocess tests for multi-repo coder workflow scripts.

Each test creates a hermetic tmp_path sandbox, seeds the minimal workspace
and plan-context.json fixtures, invokes the script as a subprocess, and
asserts the JSON output contract.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, args: list[str], cwd: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "AGENT_REPO_DIR": str(cwd)}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=env,
    )


def _seed_repo(root: Path, name: str, service_path: str, marker: str = "main.go") -> Path:
    """Create a minimal repo with agents.yml and one service marker."""
    repo = root / name
    svc = repo / service_path
    svc.mkdir(parents=True)
    (svc / marker).write_text("package main", encoding="utf-8")
    (repo / "agents.yml").write_text(
        yaml.dump({
            "repo": {"name": name},
            "workspace": {
                "type": "go-monorepo",
                "service_markers": ["main.go"],
                "qa_mode": "cli",
                "verification": "go build ./...",
            },
        }),
        encoding="utf-8",
    )
    return repo


def _seed_plan_context(spec_dir: Path, services: list[dict]) -> None:
    spec_dir.mkdir(parents=True, exist_ok=True)
    plan_ctx = {
        "services": services,
        "implementation_order": [f"{s['repo']}::{s['path']}" for s in services],
    }
    (spec_dir / "plan-context.json").write_text(json.dumps(plan_ctx, indent=2), encoding="utf-8")


def _seed_workspace_file(root: Path, folders: list[dict]) -> Path:
    ws = {"folders": folders}
    ws_file = root / "workspace.code-workspace"
    ws_file.write_text(json.dumps(ws, indent=2), encoding="utf-8")
    return ws_file


# ---------------------------------------------------------------------------
# validate-plan-context.py
# ---------------------------------------------------------------------------


def test_validate_plan_context_valid(tmp_path):
    """Valid service path with marker and plan file → status=valid."""
    _seed_repo(tmp_path, "api-service", "cmd/alert")
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "api-service", "path": "cmd/alert", "type": "go", "plan_file": "plan-alert.md"},
    ])
    (spec_dir / "plan-alert.md").write_text("# Plan", encoding="utf-8")

    ws_file = _seed_workspace_file(tmp_path, [{"name": "api-service", "path": "api-service"}])
    result = _run(
        "validate-plan-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["validation_result"]["status"] == "valid"
    assert out["validation_result"]["errors"] == []


def test_validate_plan_context_missing_marker(tmp_path):
    """Service directory exists but no main.go → status=invalid."""
    repo = tmp_path / "api-service"
    (repo / "cmd" / "alert").mkdir(parents=True)  # no main.go
    (repo / "agents.yml").write_text(
        yaml.dump({"workspace": {"service_markers": ["main.go"]}}), encoding="utf-8"
    )
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "api-service", "path": "cmd/alert", "type": "go", "plan_file": "plan.md"},
    ])
    (spec_dir / "plan.md").write_text("# Plan", encoding="utf-8")

    ws_file = _seed_workspace_file(tmp_path, [{"name": "api-service", "path": "api-service"}])
    result = _run(
        "validate-plan-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["validation_result"]["status"] == "invalid"
    assert any("marker" in e for e in out["validation_result"]["errors"])


def test_validate_plan_context_missing_plan_file(tmp_path):
    """Service is valid but plan file not written → status=invalid."""
    _seed_repo(tmp_path, "api-service", "cmd/alert")
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "api-service", "path": "cmd/alert", "type": "go", "plan_file": "plan-alert.md"},
    ])
    # plan-alert.md deliberately NOT created

    ws_file = _seed_workspace_file(tmp_path, [{"name": "api-service", "path": "api-service"}])
    result = _run(
        "validate-plan-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["validation_result"]["status"] == "invalid"
    assert any("plan file" in e for e in out["validation_result"]["errors"])


def test_validate_plan_context_unknown_repo(tmp_path):
    """Planner references a repo not in the workspace → status=invalid."""
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "nonexistent", "path": "cmd/svc", "type": "go", "plan_file": "plan.md"},
    ])
    # No workspace file → CWD-only mode (only tmp_path itself as workspace)
    result = _run("validate-plan-context.py", ["specs/s-1"], tmp_path)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["validation_result"]["status"] == "invalid"
    assert any("nonexistent" in e for e in out["validation_result"]["errors"])


def test_validate_plan_context_unknown_repo_lists_valid_keys(tmp_path):
    """An unknown repo error names the valid workspace keys so the fix is actionable."""
    _seed_repo(tmp_path, "api-service", "cmd/alert")
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "web-app", "path": "cmd/svc", "type": "go", "plan_file": "plan.md"},
    ])
    ws_file = _seed_workspace_file(tmp_path, [{"name": "api-service", "path": "api-service"}])
    result = _run(
        "validate-plan-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["validation_result"]["status"] == "invalid"
    assert any("valid: api-service" in e for e in out["validation_result"]["errors"])


def test_validate_plan_context_new_service_skips_path_check(tmp_path):
    """new_service=true skips path existence check → status=valid even when dir absent."""
    repo = tmp_path / "api-service"
    repo.mkdir(parents=True)
    (repo / "agents.yml").write_text(
        yaml.dump({"workspace": {"service_markers": ["main.go"]}}), encoding="utf-8"
    )
    # cmd/new-svc deliberately NOT created
    spec_dir = tmp_path / "specs" / "s-1"
    spec_dir.mkdir(parents=True, exist_ok=True)
    plan_ctx = {
        "services": [
            {"repo": "api-service", "path": "cmd/new-svc", "type": "go", "new_service": True, "plan_file": "plan.md"},
        ],
        "implementation_order": ["api-service::cmd/new-svc"],
    }
    (spec_dir / "plan-context.json").write_text(json.dumps(plan_ctx, indent=2), encoding="utf-8")
    (spec_dir / "plan.md").write_text("# Plan", encoding="utf-8")

    ws_file = _seed_workspace_file(tmp_path, [{"name": "api-service", "path": "api-service"}])
    result = _run(
        "validate-plan-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["validation_result"]["status"] == "valid"
    assert out["validation_result"]["errors"] == []


def test_validate_plan_context_normalizes_repo_case(tmp_path):
    """A repo that differs only by case is deterministically repaired, not rejected:
    status=valid and plan-context.json is rewritten to the canonical workspace key."""
    _seed_repo(tmp_path, "acme", "web")  # agents.yml marker is main.go
    spec_dir = tmp_path / "specs" / "s-1"
    # planner emitted the title-cased brand "Acme" instead of the folder key "acme"
    _seed_plan_context(spec_dir, [
        {"repo": "Acme", "path": "web", "type": "go", "plan_file": "plan.md"},
    ])
    (spec_dir / "plan.md").write_text("# Plan", encoding="utf-8")

    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    result = _run(
        "validate-plan-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["validation_result"]["status"] == "valid"
    assert out["validation_result"]["errors"] == []

    # file rewritten in place to the canonical key, including implementation_order
    written = json.loads((spec_dir / "plan-context.json").read_text(encoding="utf-8"))
    assert written["services"][0]["repo"] == "acme"
    assert written["implementation_order"] == ["acme::web"]


# ---------------------------------------------------------------------------
# select-next-layer.py
# ---------------------------------------------------------------------------


def _seed_two_service_plan(tmp_path: Path, ws_file: Path) -> Path:
    _seed_repo(tmp_path, "api-service", "cmd/alert")
    _seed_repo(tmp_path, "web-app", "packages/discover", marker="package.json")
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "api-service", "path": "cmd/alert", "type": "go", "plan_file": "plan-a.md"},
        {"repo": "web-app", "path": "packages/discover", "type": "svelte", "plan_file": "plan-b.md"},
    ])
    return spec_dir


def test_select_next_layer_initial(tmp_path):
    """Index=-1 → returns index 0 with has_next_layer=yes."""
    ws_file = _seed_workspace_file(tmp_path, [
        {"name": "api-service", "path": "api-service"},
        {"name": "web-app", "path": "web-app"},
    ])
    _seed_two_service_plan(tmp_path, ws_file)

    result = _run(
        "select-next-layer.py",
        ["specs/s-1", "-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_next_layer"] == "yes"
    assert out["current_layer_index"] == "0"
    assert out["current_layer"]["repo"] == "api-service"
    assert out["dispatch_count"] == "2"


def test_select_next_layer_advances(tmp_path):
    """Index=0 → returns index 1."""
    ws_file = _seed_workspace_file(tmp_path, [
        {"name": "api-service", "path": "api-service"},
        {"name": "web-app", "path": "web-app"},
    ])
    _seed_two_service_plan(tmp_path, ws_file)

    result = _run(
        "select-next-layer.py",
        ["specs/s-1", "0"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_next_layer"] == "yes"
    assert out["current_layer"]["repo"] == "web-app"


def test_select_next_layer_exhausted(tmp_path):
    """Index=1 (last) → has_next_layer=no."""
    ws_file = _seed_workspace_file(tmp_path, [
        {"name": "api-service", "path": "api-service"},
        {"name": "web-app", "path": "web-app"},
    ])
    _seed_two_service_plan(tmp_path, ws_file)

    result = _run(
        "select-next-layer.py",
        ["specs/s-1", "1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_next_layer"] == "no"
    assert out["current_layer"] == {}


def test_select_next_layer_empty_services(tmp_path):
    """No services → immediately exhausted."""
    spec_dir = tmp_path / "specs" / "s-1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "plan-context.json").write_text(json.dumps({"services": []}), encoding="utf-8")

    result = _run("select-next-layer.py", ["specs/s-1", "-1"], tmp_path)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["has_next_layer"] == "no"
    assert out["dispatch_count"] == "0"


# ---------------------------------------------------------------------------
# resolve-impl-context.py
# ---------------------------------------------------------------------------


def test_resolve_impl_context_dispatch(tmp_path):
    """Builds correct dispatch_list with CWDs and verification commands."""
    ws_file = _seed_workspace_file(tmp_path, [{"name": "api-service", "path": "api-service"}])
    _seed_repo(tmp_path, "api-service", "cmd/alert")
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "api-service", "path": "cmd/alert", "type": "go", "plan_file": "plan.md", "skills": []},
    ])

    result = _run(
        "resolve-impl-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["dispatch_count"] == "1"
    assert out["affected_repos"] == ["api-service"]

    rec = out["dispatch_list"][0]
    assert rec["repo"] == "api-service"
    assert rec["service_path"] == "cmd/alert"
    assert rec["qa_mode"] == "cli"
    assert rec["verification"] == "go build ./..."
    assert rec["cwd"] == str(tmp_path / "api-service")
    assert json.loads(out["qa_source_roots_json"]) == [
        f"api-service={tmp_path / 'api-service'}"
    ]


# ---------------------------------------------------------------------------
# resolve-review-context.py
# ---------------------------------------------------------------------------


def test_resolve_review_context_affected_repos(tmp_path):
    """Returns docs_repo_path and correct affected_repo_paths."""
    ws_file = _seed_workspace_file(tmp_path, [
        {"name": "api-service", "path": "api-service"},
        {"name": "web-app", "path": "web-app"},
    ])
    _seed_repo(tmp_path, "api-service", "cmd/alert")
    _seed_repo(tmp_path, "web-app", "packages/discover", marker="package.json")
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [
        {"repo": "api-service", "path": "cmd/alert", "type": "go", "plan_file": "plan.md"},
    ])

    result = _run(
        "resolve-review-context.py",
        ["specs/s-1"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["docs_repo_path"] == str(tmp_path)
    assert str(tmp_path / "api-service") in out["affected_repo_paths"]
    # web-app not in plan → not in affected
    assert str(tmp_path / "web-app") not in out["affected_repo_paths"]


# ---------------------------------------------------------------------------
# detect-regression-platform.py
# ---------------------------------------------------------------------------


def test_detect_regression_platform_from_services(tmp_path):
    """UI platform + touched service paths are derived from the services array."""
    spec_dir = tmp_path / "specs" / "s-1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "plan-context.json").write_text(json.dumps({
        "services": [
            {"repo": "acme", "path": "web", "type": "react-router"},
            {"repo": "acme", "path": "api", "type": "go"},
        ],
    }), encoding="utf-8")

    result = _run("detect-regression-platform.py", ["specs/s-1"], tmp_path)

    assert result.returncode == 0, result.stderr
    reg = json.loads(result.stdout)["regression"]
    assert reg["platform"] == "web"
    assert reg["layers"] == ["react-router"]
    # The touched web service is pinned to its repo::path, so the gate can scope.
    assert reg["paths"] == ["acme::web"]


def test_detect_regression_platform_non_ui_is_none(tmp_path):
    spec_dir = tmp_path / "specs" / "s-1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "plan-context.json").write_text(json.dumps({
        "services": [{"repo": "acme", "path": "api", "type": "go"}],
    }), encoding="utf-8")

    result = _run("detect-regression-platform.py", ["specs/s-1"], tmp_path)

    assert result.returncode == 0, result.stderr
    reg = json.loads(result.stdout)["regression"]
    assert reg["platform"] == "none"
    assert reg["paths"] == []


def test_detect_regression_platform_legacy_touched_layers(tmp_path):
    """Legacy flat touched_layers (no services array) still resolves via fallback."""
    spec_dir = tmp_path / "specs" / "s-1"
    spec_dir.mkdir(parents=True)
    (spec_dir / "plan-context.json").write_text(json.dumps({
        "touched_layers": ["go", "react-router"],
    }), encoding="utf-8")

    result = _run("detect-regression-platform.py", ["specs/s-1"], tmp_path)

    assert result.returncode == 0, result.stderr
    reg = json.loads(result.stdout)["regression"]
    assert reg["platform"] == "web"
    assert reg["layers"] == ["react-router"]
    # No per-service scoping available in the legacy form.
    assert reg["paths"] == []
