"""Direct subprocess tests for the deterministic-run + fix + reverify regression
loop scripts: run-regression-suite.py, incr_regression_fix.py, and
mark-regression-unresolved.py.

Same hermetic-sandbox style as test_multi_repo_scripts.py: seed a tmp_path
workspace + plan-context.json, invoke the script as a subprocess, assert the
JSON output contract. `make e2e-journeys` is faked via a real Makefile in the
resolved service cwd so these tests exercise the actual exit-code/output
parsing without needing a live stack.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml
from workhorse.builtins import incr

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(
    script: str, args: list[str], cwd: Path, extra_env: dict | None = None
) -> subprocess.CompletedProcess:
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


def _seed_web_service(
    root: Path, repo_name: str, service_path: str, makefile_body: str
) -> Path:
    """Create a minimal repo with an agents.yml and a fake `make e2e-journeys` target."""
    repo = root / repo_name
    svc = repo / service_path
    svc.mkdir(parents=True)
    (svc / "Makefile").write_text(makefile_body, encoding="utf-8")
    (repo / "agents.yml").write_text(
        yaml.dump({"repo": {"name": repo_name}, "workspace": {"type": "react-router"}}),
        encoding="utf-8",
    )
    return repo


def _seed_plan_context(spec_dir: Path, services: list[dict]) -> None:
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "plan-context.json").write_text(
        json.dumps({"services": services}, indent=2), encoding="utf-8"
    )


def _seed_qa_context(spec_dir: Path, verification_index: list[dict]) -> None:
    (spec_dir / "qa-okf-context.json").write_text(
        json.dumps({"version": 1, "verificationIndex": verification_index}, indent=2),
        encoding="utf-8",
    )


def _seed_workspace_file(root: Path, folders: list[dict]) -> Path:
    ws_file = root / "workspace.code-workspace"
    ws_file.write_text(json.dumps({"folders": folders}, indent=2), encoding="utf-8")
    return ws_file


# ---------------------------------------------------------------------------
# run-regression-suite.py
# ---------------------------------------------------------------------------


def test_run_regression_suite_none_platform_passes_without_running_anything(tmp_path):
    """platform=none (no UI layer touched) → passed, nothing invoked."""
    spec_dir = tmp_path / "specs" / "s-1"
    spec_dir.mkdir(parents=True)

    result = _run("run-regression-suite.py", ["specs/s-1", "", "none"], tmp_path)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "passed"
    assert out["regression_run"]["failing_tests"] == []
    assert out["qa_result"] == {
        "status": "passed",
        "notes": out["regression_run"]["notes"],
    }


def test_run_regression_suite_web_passed(tmp_path):
    """`make e2e-journeys` exits 0 → status=passed, qa_result mirrors it."""
    makefile = "e2e-journeys:\n\t@exit 0\n"
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )
    qa_dir = tmp_path / "specs" / "s-1" / "qa"

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", str(qa_dir), "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "passed"
    assert out["regression_run"]["failing_tests"] == []
    assert out["qa_result"]["status"] == "passed"
    assert any(f.name.startswith("regression-run-web") for f in qa_dir.iterdir())


def test_run_regression_suite_web_failed_parses_failing_tests(tmp_path):
    """Non-zero exit with playwright-style failure lines → status=failed with parsed tests."""
    makefile = (
        "e2e-journeys:\n"
        "\t@echo '  1) [journeys] › e2e/journeys/foo.journey.spec.ts:12:3 › does the thing'\n"
        "\t@exit 1\n"
    )
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )
    qa_dir = tmp_path / "specs" / "s-1" / "qa"

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", str(qa_dir), "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    run = out["regression_run"]
    assert run["status"] == "failed"
    assert len(run["failing_tests"]) == 1
    assert "foo.journey.spec.ts" in run["failing_tests"][0]
    assert "does the thing" in run["failing_tests"][0]
    assert out["qa_result"]["status"] == "failed"
    assert out["qa_result"]["notes"] == run["notes"]


def test_run_regression_suite_fails_okf_grounded_outside_impact_failure(tmp_path):
    makefile = (
        "e2e-journeys:\n"
        "\t@echo '  1) [journeys] › e2e/journeys/accounts.spec.ts:12:3 › login works'\n"
        "\t@exit 1\n"
    )
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )
    _seed_qa_context(
        spec_dir,
        [
            {
                "node": "docs/features/acme/flows/account-login.md",
                "ref": "web/e2e/journeys/accounts.spec.ts::login works",
                "path": "web/e2e/journeys/accounts.spec.ts",
                "impacted": False,
            }
        ],
    )

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", str(spec_dir / "qa"), "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    run = json.loads(result.stdout)["regression_run"]
    assert run["status"] == "failed"
    assert run["failure_attribution"][0]["classification"] == "outside-impact"
    assert len(run["failing_tests"]) == 1
    assert not (spec_dir / "backlog-items.json").exists()


def test_run_regression_suite_fails_okf_grounded_impacted_failure(tmp_path):
    makefile = (
        "e2e-journeys:\n"
        "\t@echo '  1) [journeys] › e2e/journeys/items.spec.ts:12:3 › create item'\n"
        "\t@exit 1\n"
    )
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )
    _seed_qa_context(
        spec_dir,
        [
            {
                "node": "docs/features/acme/flows/item-create.md",
                "ref": "web/e2e/journeys/items.spec.ts::create item",
                "path": "web/e2e/journeys/items.spec.ts",
                "impacted": True,
            }
        ],
    )

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", str(spec_dir / "qa"), "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    run = json.loads(result.stdout)["regression_run"]
    assert run["status"] == "failed"
    assert run["failure_attribution"][0]["classification"] == "impacted"
    assert not (spec_dir / "backlog-items.json").exists()


def test_run_regression_suite_keeps_all_mixed_failures_in_fix_worklist(tmp_path):
    makefile = (
        "e2e-journeys:\n"
        "\t@echo '  1) [journeys] › e2e/journeys/items.spec.ts:12:3 › create item'\n"
        "\t@echo '  2) [journeys] › e2e/journeys/accounts.spec.ts:8:3 › login works'\n"
        "\t@exit 1\n"
    )
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )
    _seed_qa_context(
        spec_dir,
        [
            {"node": "item-flow", "path": "web/e2e/journeys/items.spec.ts", "impacted": True},
            {
                "node": "account-flow",
                "path": "web/e2e/journeys/accounts.spec.ts",
                "impacted": False,
            },
        ],
    )

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", str(spec_dir / "qa"), "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    run = json.loads(result.stdout)["regression_run"]
    assert run["status"] == "failed"
    assert len(run["failing_tests"]) == 2
    assert {item["classification"] for item in run["failure_attribution"]} == {
        "impacted",
        "outside-impact",
    }
    assert not (spec_dir / "backlog-items.json").exists()


def test_run_regression_suite_web_blocked_when_stack_unreachable(tmp_path):
    """`not reachable on :` in output → status=blocked, not failed."""
    makefile = "e2e-journeys:\n\t@echo 'web not reachable on :3000'\n\t@exit 1\n"
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )
    qa_dir = tmp_path / "specs" / "s-1" / "qa"

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", str(qa_dir), "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "blocked"
    assert out["regression_run"]["failing_tests"] == []
    assert "not reachable" in out["regression_run"]["notes"]
    assert out["qa_result"]["status"] == "blocked"


def test_run_regression_suite_web_blocked_when_service_missing(tmp_path):
    """plan-context has no react-router/svelte service → blocked, explanatory notes."""
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [{"repo": "acme", "path": "api", "type": "go"}])

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", "", "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "blocked"
    assert "no matching service" in out["regression_run"]["notes"]


def test_run_regression_suite_web_skip_no_makefile(tmp_path):
    """Web service without a Makefile → passed (skip), not blocked."""
    repo = tmp_path / "acme"
    svc = repo / "web"
    svc.mkdir(parents=True)
    # No Makefile created
    (repo / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "acme"}, "workspace": {"type": "react-router"}}),
        encoding="utf-8",
    )
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", "", "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "passed"
    assert "skipped" in out["regression_run"]["notes"]
    assert out["qa_result"]["status"] == "passed"


def test_run_regression_suite_web_skip_no_target(tmp_path):
    """Makefile exists but has no e2e-journeys target → passed (skip)."""
    makefile = "lint:\n\t@exit 0\n"
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(tmp_path, [{"name": "acme", "path": "acme"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir, [{"repo": "acme", "path": "web", "type": "react-router"}]
    )

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", "", "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "passed"
    assert "skipped" in out["regression_run"]["notes"]
    assert out["qa_result"]["status"] == "passed"


def test_run_regression_suite_mobile_skip_no_maestro_flows(tmp_path):
    """Flutter service without maestro_flows/ → passed (skip), not blocked."""
    repo = tmp_path / "mobile-app"
    svc = repo / "."
    svc.mkdir(parents=True)
    # No maestro_flows/ directory created
    (repo / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "mobile-app"}, "workspace": {"type": "flutter"}}),
        encoding="utf-8",
    )
    ws_file = _seed_workspace_file(tmp_path, [{"name": "mobile-app", "path": "mobile-app"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [{"repo": "mobile-app", "path": ".", "type": "flutter"}])

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", "", "mobile"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "passed"
    assert "skipped" in out["regression_run"]["notes"]
    assert "maestro_flows" in out["regression_run"]["notes"]
    assert out["qa_result"]["status"] == "passed"


def test_run_regression_suite_mobile_skip_empty_maestro_flows(tmp_path):
    """Flutter service with an empty maestro_flows/ (no flow files) → passed (skip),
    not failed. `maestro test` on an empty dir exits non-zero with "do not contain
    any Flow files" — this must not be misclassified as a real regression failure."""
    repo = tmp_path / "mobile-app"
    svc = repo / "."
    (svc / "maestro_flows").mkdir(parents=True)
    (repo / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "mobile-app"}, "workspace": {"type": "flutter"}}),
        encoding="utf-8",
    )
    ws_file = _seed_workspace_file(tmp_path, [{"name": "mobile-app", "path": "mobile-app"}])
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(spec_dir, [{"repo": "mobile-app", "path": ".", "type": "flutter"}])

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", "", "mobile"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "passed"
    assert "skipped" in out["regression_run"]["notes"]
    assert "maestro_flows" in out["regression_run"]["notes"]
    assert out["qa_result"]["status"] == "passed"


def test_run_regression_suite_multi_service_all_skip(tmp_path):
    """Multiple web services all missing suites → overall passed."""
    # Service 1: no Makefile
    repo1 = tmp_path / "web-app"
    (repo1 / "packages" / "discover").mkdir(parents=True)
    (repo1 / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "web-app"}, "workspace": {"type": "svelte"}}),
        encoding="utf-8",
    )
    # Service 2: no Makefile
    repo2 = tmp_path / "acme"
    (repo2 / "web").mkdir(parents=True)
    (repo2 / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "acme"}, "workspace": {"type": "react-router"}}),
        encoding="utf-8",
    )
    ws_file = _seed_workspace_file(
        tmp_path,
        [
            {"name": "web-app", "path": "web-app"},
            {"name": "acme", "path": "acme"},
        ],
    )
    spec_dir = tmp_path / "specs" / "s-1"
    _seed_plan_context(
        spec_dir,
        [
            {"repo": "web-app", "path": "packages/discover", "type": "svelte"},
            {"repo": "acme", "path": "web", "type": "react-router"},
        ],
    )

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", "", "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "passed"
    assert out["qa_result"]["status"] == "passed"


def test_run_regression_suite_multi_service_mixed(tmp_path):
    """One service skips (no Makefile), one fails → overall failed."""
    # Service 1: no Makefile (skips)
    repo1 = tmp_path / "web-app"
    (repo1 / "packages" / "discover").mkdir(parents=True)
    (repo1 / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "web-app"}, "workspace": {"type": "svelte"}}),
        encoding="utf-8",
    )
    # Service 2: has Makefile that fails
    makefile = (
        "e2e-journeys:\n"
        "\t@echo '  1) [journeys] › e2e/journeys/login.spec.ts:5:3 › login works'\n"
        "\t@exit 1\n"
    )
    _seed_web_service(tmp_path, "acme", "web", makefile)
    ws_file = _seed_workspace_file(
        tmp_path,
        [
            {"name": "web-app", "path": "web-app"},
            {"name": "acme", "path": "acme"},
        ],
    )
    spec_dir = tmp_path / "specs" / "s-1"
    qa_dir = tmp_path / "specs" / "s-1" / "qa"
    _seed_plan_context(
        spec_dir,
        [
            {"repo": "web-app", "path": "packages/discover", "type": "svelte"},
            {"repo": "acme", "path": "web", "type": "react-router"},
        ],
    )

    result = _run(
        "run-regression-suite.py",
        ["specs/s-1", str(qa_dir), "web"],
        tmp_path,
        extra_env={"CODER_WORKSPACE": str(ws_file)},
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["regression_run"]["status"] == "failed"
    assert len(out["regression_run"]["failing_tests"]) >= 1
    assert out["qa_result"]["status"] == "failed"


# ---------------------------------------------------------------------------
# incr built-in (replaces the deleted incr_regression_fix.py script)
# ---------------------------------------------------------------------------


def test_incr_regression_fix_from_zero():
    assert incr(0) == 1


def test_incr_regression_fix_bumps_existing_value():
    assert incr(2) == 3


def test_incr_regression_fix_missing_arg_treated_as_zero():
    assert incr() == 1


# ---------------------------------------------------------------------------
# mark-regression-unresolved.py
# ---------------------------------------------------------------------------


def test_mark_regression_unresolved_includes_notes_and_attempts(tmp_path):
    result = _run(
        "mark-regression-unresolved.py",
        ["make e2e-journeys exited 1; 2 failing test(s): foo.spec.ts", "3"],
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["qa_result"]["status"] == "failed"
    assert "3 fix attempt(s)" in out["qa_result"]["notes"]
    assert "foo.spec.ts" in out["qa_result"]["notes"]


def test_mark_regression_unresolved_defaults_when_args_missing(tmp_path):
    result = _run("mark-regression-unresolved.py", [], tmp_path)

    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["qa_result"]["status"] == "failed"
    assert "3 fix attempt(s)" in out["qa_result"]["notes"]
    assert "no failure detail captured" in out["qa_result"]["notes"]
