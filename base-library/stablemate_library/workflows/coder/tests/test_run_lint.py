"""Direct subprocess tests for run-lint.py — the deterministic half of the coder lint gate.

Same hermetic style as test_regression_fix_scripts.py: seed a tmp service dir with a real
Makefile (or agents.yml override) and assert the JSON status contract, exercising the actual
exit-code/output parsing without a live stack.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "AGENT_REPO_DIR": str(cwd)}
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "run-lint.py"), *args],
        capture_output=True, text=True, cwd=str(cwd), env=env,
    )


def _svc(root: Path, name: str, makefile: str | None) -> Path:
    svc = root / name
    svc.mkdir(parents=True)
    if makefile is not None:
        (svc / "Makefile").write_text(makefile, encoding="utf-8")
    return svc


def test_make_lint_clean(tmp_path):
    svc = _svc(tmp_path, "groom", "lint:\n\t@echo ok; exit 0\n")
    out = json.loads(_run([str(svc), "groom"], tmp_path).stdout)
    assert out["lint_status"] == "clean"
    assert out["lint_command"] == "make lint"


def test_make_lint_dirty_captures_output(tmp_path):
    svc = _svc(tmp_path, "groom", "lint:\n\t@echo 'A11Y002 missing label'; exit 1\n")
    out = json.loads(_run([str(svc), "groom"], tmp_path).stdout)
    assert out["lint_status"] == "dirty"
    assert "A11Y002 missing label" in out["lint_output"]


def test_no_lint_target_is_skipped(tmp_path):
    # a Makefile without a `lint` target → opt-out, never a false failure
    svc = _svc(tmp_path, "workhorse", "build:\n\t@exit 0\n")
    out = json.loads(_run([str(svc), "workhorse"], tmp_path).stdout)
    assert out["lint_status"] == "skipped"


def test_no_makefile_is_skipped(tmp_path):
    svc = _svc(tmp_path, "ostler", None)
    out = json.loads(_run([str(svc), "ostler"], tmp_path).stdout)
    assert out["lint_status"] == "skipped"


def test_agents_yml_override_wins_over_convention(tmp_path):
    # even with a passing `make lint`, an explicit override is the command that runs
    svc = _svc(tmp_path, "groom", "lint:\n\t@exit 0\n")
    (tmp_path / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "r"}, "lint": {"groom": "sh -c 'exit 1'"}}),
        encoding="utf-8",
    )
    out = json.loads(_run([str(svc), "groom"], tmp_path).stdout)
    assert out["lint_status"] == "dirty"
    assert out["lint_command"] == "sh -c 'exit 1'"


def test_override_under_workflow_key(tmp_path):
    svc = _svc(tmp_path, "groom", None)
    (tmp_path / "agents.yml").write_text(
        yaml.dump({"repo": {"name": "r"}, "workflow": {"lint": {"groom": "true"}}}),
        encoding="utf-8",
    )
    out = json.loads(_run([str(svc), "groom"], tmp_path).stdout)
    assert out["lint_status"] == "clean"
    assert out["lint_command"] == "true"


def test_missing_cwd_is_skipped(tmp_path):
    out = json.loads(_run([str(tmp_path / "nope"), "x"], tmp_path).stdout)
    assert out["lint_status"] == "skipped"
