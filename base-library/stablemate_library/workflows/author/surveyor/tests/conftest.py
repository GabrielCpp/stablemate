"""Shared fixtures/helpers for surveyor-workflow script tests.

The surveyor's correctness lives in its deterministic Python scripts (the enumeration
expander, the loop driver, the record/partition validators, the coverage gate). Unlike
author, none of them shells out to ostler — the survey layer is plain JSON/YAML/markdown
on disk — so these are straight subprocess tests: build a fixture repo, run each script
with ``AGENT_REPO_DIR`` pointed at it (the same way the local-worker runs them), and
assert on the emitted JSON.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent / "scripts"


def run_script(name: str, *args: str, repo: Path) -> dict:
    """Run scripts/<name> with AGENT_REPO_DIR=repo; return parsed JSON stdout.

    Raises AssertionError (with stderr) if the script exits non-zero or its stdout
    is not JSON — both are real failures for the nodes that consume these scripts.
    """
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 0, f"{name} exited {proc.returncode}\nstderr:\n{proc.stderr}"
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:  # pragma: no cover - failure path
        raise AssertionError(f"{name} stdout not JSON: {e}\nstdout:\n{proc.stdout}")


def run_script_raw(name: str, *args: str, repo: Path) -> subprocess.CompletedProcess:
    """Run scripts/<name> and return the raw CompletedProcess (for exit-code tests)."""
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        capture_output=True, text=True, env=env,
    )


def init_repo(repo: Path, *, rubric: bool = True) -> None:
    """Lay down the minimum a fixture repo needs: a root marker + (usually) a rubric."""
    (repo / "agents.yml").write_text("name: testrepo\n", encoding="utf-8")
    if rubric:
        (repo / "docs" / "survey").mkdir(parents=True, exist_ok=True)
        (repo / "docs" / "survey" / "rubric.md").write_text(
            "# Rubric: test concern\n\nEvery unit must frobnicate.\n", encoding="utf-8"
        )


def git_repo(repo: Path) -> None:
    """Turn the fixture into a git repo with everything committed (baseline tests)."""
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                       env=dict(os.environ,
                                GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                                GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "baseline", "--no-gpg-sign")


# ── Fixture builders (the on-disk forms the scripts read/write) ────────────────────────

def write_inventory(repo: Path, units: list[dict], *,
                    rules: str = "docs/survey/units.yml",
                    path: str = "docs/survey/inventory.json") -> Path:
    """Write an inventory.json. ``units`` entries: {id, path?, kind?, status?}."""
    full = [{"id": u["id"], "path": u.get("path", u["id"]),
             "kind": u.get("kind", "folder"), "status": u.get("status", "pending")}
            for u in units]
    inv = repo / path
    inv.parent.mkdir(parents=True, exist_ok=True)
    inv.write_text(json.dumps({"version": 1, "rules": rules, "units": full}, indent=2) + "\n",
                   encoding="utf-8")
    return inv


def record_slug(unit_id: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", unit_id.lower()).strip("-")


def write_record(repo: Path, unit_id: str, *, status: str = "assessed",
                 kind: str = "folder", findings: list[dict] | None = None,
                 open_gaps: list[str] | None = None, disposition: str | None = None,
                 findings_dir: str = "docs/survey/findings",
                 front_matter_extra: str = "") -> Path:
    """Write a finding record. Defaults produce a VALID `assessed` record."""
    if findings is None and status == "assessed":
        findings = [{"description": "missing frobnication",
                     "remediation_pattern": "add-frobnication",
                     "effort": "small", "evidence": f"{unit_id}/main.ts:1 — no frob call"}]
    lines = ["---", "type: survey-finding", f"unit: {unit_id}", f"kind: {kind}",
             f"status: {status}"]
    if findings:
        lines.append("findings:")
        for f in findings:
            lines.append(f"  - description: {json.dumps(f.get('description', ''))}")
            for key in ("remediation_pattern", "effort", "evidence"):
                if key in f:
                    lines.append(f"    {key}: {json.dumps(f[key])}")
    else:
        lines.append("findings: []")
    if open_gaps:
        lines.append("openGaps:")
        lines.extend(f"  - {json.dumps(g)}" for g in open_gaps)
    if disposition:
        lines.append(f"disposition: {disposition}")
    if front_matter_extra:
        lines.append(front_matter_extra)
    lines += ["---", "", f"# Survey finding: {unit_id}", ""]
    rec = repo / findings_dir / f"{record_slug(unit_id)}.md"
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text("\n".join(lines), encoding="utf-8")
    return rec


def write_rules(repo: Path, body: str, *, path: str = "docs/survey/units.yml") -> Path:
    rules = repo / path
    rules.parent.mkdir(parents=True, exist_ok=True)
    rules.write_text(body, encoding="utf-8")
    return rules


def write_partition(repo: Path, clusters: list[dict], *,
                    path: str = "docs/survey/partition.yaml") -> Path:
    """Write a partition.yaml. ``clusters`` entries pass through with defaults filled."""
    lines = ["clusters:"]
    for c in clusters:
        lines.append(f"  - id: {c['id']}")
        lines.append(f"    title: {json.dumps(c.get('title', 'Fix ' + c['id']))}")
        lines.append(f"    remediation_pattern: {c.get('remediation_pattern', c['id'])}")
        lines.append(f"    strategy: {c.get('strategy', 'mechanical')}")
        if "order" in c:
            lines.append(f"    order: {c['order']}")
        lines.append("    units:")
        lines.extend(f"      - {u}" for u in c.get("units", []))
        if c.get("notes"):
            lines.append(f"    notes: {json.dumps(c['notes'])}")
    part = repo / path
    part.parent.mkdir(parents=True, exist_ok=True)
    part.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return part
