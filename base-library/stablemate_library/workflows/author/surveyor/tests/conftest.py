"""Shared fixtures/helpers for surveyor-workflow script tests.

The surveyor's correctness lives in its deterministic Python scripts (the enumeration
expander, the loop driver, the record/partition validators, the coverage gate). Unlike
author, none of them shells out to ostler or the ``gh`` CLI — the survey layer is plain
JSON/YAML/markdown on disk (``verify-records`` reads a git baseline via real ``git``).

The scripts are exercised through workhorse's **in-process** harness: :class:`workhorse
.testing.InProcessScriptRunner` runs each script via ``runpy`` in the current process (no
``python <script>`` subprocess, no PATH shims), with ``AGENT_REPO_DIR`` pointed at a
fixture repo — the same way the local-worker's in-process script runner invokes them.
Git operations run for real against a throwaway repo seeded with
:func:`workhorse.testing.make_git_repo`; nothing about git is mocked.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from workhorse.testing import InProcessScriptRunner, make_git_repo

SCRIPTS = Path(__file__).parent.parent / "scripts"

_RUNNER = InProcessScriptRunner()


def run_script(name: str, *args: str, repo: Path) -> dict:
    """Run scripts/<name> IN-PROCESS with AGENT_REPO_DIR=repo; return parsed JSON stdout.

    Raises AssertionError (with stderr) if the script exits non-zero or its stdout
    is not JSON — both are real failures for the nodes that consume these scripts.
    """
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    code, out, err = _RUNNER.run(SCRIPTS / name, list(args), str(repo), env)
    assert code == 0, f"{name} exited {code}\nstderr:\n{err}"
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:  # pragma: no cover - failure path
        raise AssertionError(f"{name} stdout not JSON: {e}\nstdout:\n{out}")


def run_script_raw(name: str, *args: str, repo: Path) -> subprocess.CompletedProcess:
    """Run scripts/<name> IN-PROCESS; return a CompletedProcess (for exit-code tests)."""
    env = dict(os.environ, AGENT_REPO_DIR=str(repo))
    code, out, err = _RUNNER.run(SCRIPTS / name, list(args), str(repo), env)
    return subprocess.CompletedProcess(
        args=[str(SCRIPTS / name), *args], returncode=code, stdout=out, stderr=err
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
    """Turn the fixture into a REAL git repo with everything committed (baseline tests).

    Delegates to :func:`workhorse.testing.make_git_repo`, which inits a repo (no origin)
    and commits every file present — the frozen baseline ``verify-records`` reads back
    with ``git show HEAD:<path>``. Git is exercised for real, never mocked.
    """
    make_git_repo(repo, name="testrepo")


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
