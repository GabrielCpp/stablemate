"""Tests for ostler-doctor.py — the referential-integrity gate node.

The script shells out to `ostler doctor --json`; these tests put a fake `ostler` on PATH
that emits canned reports, so they exercise the gate's mapping (errors block, warnings
don't, missing tool skips) without depending on a real ostler install or a doc graph.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "ostler-doctor.py"


def _fake_ostler(bin_dir: Path, report: dict, exit_code: int = 0) -> Path:
    """Write an executable fake `ostler` that prints `report` as JSON and exits `exit_code`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    ostler = bin_dir / "ostler"
    ostler.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, json\n"
        f"print(json.dumps({report!r}))\n"
        f"sys.exit({exit_code})\n"
    )
    ostler.chmod(0o755)
    return ostler


def _run(repo: Path, path: str | None, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env,
    )


def _report(findings: list[dict]) -> dict:
    return {"org": "T", "profile": "full", "epics": [], "findings": findings,
            "errors": sum(f["severity"] == "error" for f in findings),
            "warnings": sum(f["severity"] == "warn" for f in findings)}


def test_clean_graph_passes(tmp_path):
    _fake_ostler(tmp_path / "bin", _report([]))
    proc = _run(tmp_path, f"{tmp_path/'bin'}:{os.environ['PATH']}")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["integrity_ok"] == "yes"
    assert out["integrity_errors"] == ""


def test_errors_block_with_pointers(tmp_path):
    findings = [{"severity": "error", "code": "dangling-owner", "epic": "",
                 "ref": "gap-x", "message": "gap 'gap-x' owned by unknown story 'gone'"}]
    _fake_ostler(tmp_path / "bin", _report(findings), exit_code=1)  # ostler exits non-zero on breaks
    proc = _run(tmp_path, f"{tmp_path/'bin'}:{os.environ['PATH']}")
    assert proc.returncode == 0, proc.stderr  # gate must NOT propagate ostler's non-zero exit
    out = json.loads(proc.stdout)
    assert out["integrity_ok"] == "no"
    assert "dangling-owner" in out["integrity_errors"]
    assert "gone" in out["integrity_errors"]
    # the constraint that the resolver must not erase the ref is part of the pointer
    assert "never" in out["integrity_errors"].lower()


def test_warnings_do_not_block(tmp_path):
    findings = [{"severity": "warn", "code": "stale-owner", "ref": "g", "message": "no owner"}]
    _fake_ostler(tmp_path / "bin", _report(findings))
    proc = _run(tmp_path, f"{tmp_path/'bin'}:{os.environ['PATH']}")
    out = json.loads(proc.stdout)
    assert out["integrity_ok"] == "yes"
    assert "1 warning" in out["integrity_report"]


def test_skip_when_ostler_absent(tmp_path):
    # PATH without any ostler → clean skip, never a block, exit 0.
    proc = _run(tmp_path, "/nonexistent-bin-dir")
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["integrity_ok"] == "skip"
    assert "not installed" in out["integrity_report"]
