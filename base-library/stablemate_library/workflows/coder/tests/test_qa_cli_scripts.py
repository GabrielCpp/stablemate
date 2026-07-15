"""Tests for the thin Ostler QA command adapters and four-state routing JSON."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"


def install_fake_ostler(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    executable = bin_dir / "ostler"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
record = os.environ.get("OSTLER_ARGS_FILE")
if record:
    Path(record).write_text(json.dumps(args), encoding="utf-8")

subcommand = args[1] if len(args) > 1 and args[0] == "qa" else ""
if subcommand == "context":
    status = os.environ.get("OSTLER_CONTEXT_STATUS", "passed")
    payload = {"status": status, "healthFindings": ["unmapped"] if status == "invalid" else []}
elif subcommand == "context-validate":
    status = os.environ.get("OSTLER_CONTEXT_VALIDATE_STATUS", "passed")
    payload = {"status": status, "problems": [] if status == "passed" else ["bad context"]}
elif subcommand == "validate":
    status = os.environ.get("OSTLER_VALIDATE_STATUS", "passed")
    payload = {"status": status}
elif subcommand == "run":
    status = os.environ.get("OSTLER_RUN_STATUS", "passed")
    payload = {"status": status, "notes": f"runner {status}"}
else:
    payload = {"status": "invalid"}
    status = "invalid"

print(json.dumps(payload))
sys.exit(0 if status == "passed" else 1)
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return bin_dir


def run_script(tmp_path: Path, script: str, args: list[str], **extra_env: str) -> dict:
    bin_dir = install_fake_ostler(tmp_path)
    env = {
        **os.environ,
        "PATH": str(bin_dir) + os.pathsep + os.environ.get("PATH", ""),
        **extra_env,
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize("status", ["passed", "failed", "blocked", "invalid"])
def test_run_adapter_preserves_all_expected_statuses(
    tmp_path: Path, status: str
) -> None:
    output = run_script(
        tmp_path,
        "run-qa-plan.py",
        [str(tmp_path / "spec")],
        OSTLER_RUN_STATUS=status,
    )
    assert output["qa_result"]["status"] == status


def test_build_context_passes_required_cli_arguments_and_normalizes_exit_one(
    tmp_path: Path,
) -> None:
    args_file = tmp_path / "args.json"
    spec = tmp_path / "spec"
    story = tmp_path / "story.md"
    features = tmp_path / "docs" / "features"
    output = run_script(
        tmp_path,
        "build-qa-okf-context.py",
        [
            str(spec),
            str(story),
            str(features),
            json.dumps([f"api={tmp_path / 'api'}", f"web={tmp_path / 'web'}"]),
            "base-ref",
            "WORKTREE",
            str(tmp_path),
        ],
        OSTLER_CONTEXT_STATUS="invalid",
        OSTLER_ARGS_FILE=str(args_file),
    )

    assert output["qa_context_build"]["status"] == "invalid"
    args = json.loads(args_file.read_text(encoding="utf-8"))
    assert args[:6] == ["qa", "context", "--base", "base-ref", "--head", "WORKTREE"]
    assert args.count("--source-root") == 2
    assert "--story-file" in args
    assert args[-1] == "--json"


def test_context_and_plan_validation_normalize_invalid(tmp_path: Path) -> None:
    context = run_script(
        tmp_path,
        "validate-qa-okf-context.py",
        [str(tmp_path / "spec"), "passed"],
        OSTLER_CONTEXT_VALIDATE_STATUS="invalid",
    )
    plan = run_script(
        tmp_path,
        "validate-qa-plan.py",
        [str(tmp_path / "spec")],
        OSTLER_VALIDATE_STATUS="invalid",
    )
    assert context["qa_context_result"]["status"] == "invalid"
    assert plan["qa_plan_validation"]["status"] == "invalid"
