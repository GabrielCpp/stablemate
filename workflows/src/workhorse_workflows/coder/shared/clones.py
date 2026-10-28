"""The lap's clone check: runs the code-structure skill's script and turns each copy into a finding."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from git.exc import GitError
from workhorse._vendor.stablemate_core.base_cache import cache_root
from workhorse.pyflow import WorkflowFailed

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.okf import story_base
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import CopyCheck

SCRIPT_GLOB = "library/skills/**/code-structure/scripts/check_clones.py"
CHECK_TIMEOUT = 600
COINCIDENCE_CONFIG = ".agent-checks.toml"

REPAIR = (
    "extract the repeated code to one owner both callers use, in this change "
    "(code-structure rule 2.12). When the two change for different reasons, add a "
    f"[[check-clones.coincidence]] entry to {COINCIDENCE_CONFIG} naming both files and two "
    "different reasons instead."
)
CROSS_BUILD_REPAIR = (
    "extract the repeated code to a library the repository's workspace lists and each build "
    "declares, in this change (code-structure rule 2.13). When the repository has no workspace, "
    "or a build context, CI path filter or deploy has to widen, and no docs/decisions record "
    "covers it, propose the library and return blocked instead. When the two change for "
    f"different reasons, add a [[check-clones.coincidence]] entry to {COINCIDENCE_CONFIG} naming "
    "both files and two different reasons instead."
)
PROBLEM_REPAIR = "give the entry two different reasons, one per file, or remove it"


def check_script(library_dirs: tuple[str, ...]) -> Path | None:
    """The first layer's copy of the clone check script, in layer order."""
    for layer in library_dirs:
        for candidate in sorted(Path(layer).glob(SCRIPT_GLOB)):
            if candidate.is_file():
                return candidate
    return None


def _repositories(roots: list[str]) -> list[Path]:
    seen: list[Path] = []
    for root in roots:
        if not root:
            continue
        done = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        top = Path(done.stdout.strip()) if done.returncode == 0 and done.stdout.strip() else Path(root)
        if top not in seen:
            seen.append(top)
    return seen


def _run(script: Path, root: Path, base: str) -> dict:
    env = {**os.environ, "STABLEMATE_CACHE_DIR": str(cache_root())}
    try:
        done = subprocess.run(
            [sys.executable, "-I", str(script), "--root", str(root), "--base", base, "--json"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=CHECK_TIMEOUT,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkflowFailed(
            f"the clone check did not finish in {root} within {CHECK_TIMEOUT} s"
        ) from exc
    report = None
    if done.returncode in (0, 1):
        try:
            report = json.loads(done.stdout)
        except json.JSONDecodeError:
            report = None
    if not isinstance(report, dict):
        raise WorkflowFailed(
            f"the clone check could not run in {root}:\n{done.stderr.strip()}"
        )
    return report


def _named(side: dict) -> str:
    return f"{side['path']}:{side['start']}-{side['end']}"


def _pair_finding(repo: Path, pair: dict) -> Finding:
    added, existing = pair["added"], pair["existing"]
    sits = f" The copy sits in {added['unit']}." if added.get("unit") else ""
    unit = f" ({existing['unit']})" if existing.get("unit") else ""
    builds = (added.get("build"), existing.get("build"))
    across = builds[0] is not None and builds[1] is not None and builds[0] != builds[1]
    split = f" The two sit in separate builds, {builds[0]} and {builds[1]}." if across else ""
    return Finding(
        target=f"{repo.name}/{_named(added)}",
        issue=(
            f"this story added a copy of {_named(existing)}{unit}, {pair['lines']} lines.{sits}{split} "
            "The two will change for the same reason and get fixed in one place only."
        ),
        repair=CROSS_BUILD_REPAIR if across else REPAIR,
    )


@blueprint.node
def check_copies(
    logger: logging.Logger,
    roots: list[str],
    story_slug: str = "",
    story_id: str = "",
    library_dirs: tuple[str, ...] = (),
) -> CopyCheck:
    """Findings for each copy this story added in the first repository that has one."""
    script = check_script(library_dirs)
    if script is None:
        searched = ", ".join(library_dirs) or "no library layer"
        raise WorkflowFailed(
            f"no {SCRIPT_GLOB} in any library layer searched: {searched}"
        )
    refs = tuple(dict.fromkeys(ref for ref in (story_id, story_slug) if ref))
    for repo in _repositories(roots):
        try:
            base = story_base(repo, refs)
        except (GitError, ValueError) as exc:
            raise WorkflowFailed(f"the clone check found no story base in {repo}: {exc}") from exc
        report = _run(script, repo, base)
        findings = [_pair_finding(repo, pair) for pair in report.get("pairs", [])]
        findings += [
            Finding(
                target=f"{repo.name}/{COINCIDENCE_CONFIG}",
                issue=str(problem),
                repair=PROBLEM_REPAIR,
            )
            for problem in report.get("problems", [])
        ]
        logger.info("clone check in %s from %s: %d finding(s)", repo, base, len(findings))
        if findings:
            return CopyCheck(findings=findings, cwd=str(repo))
    return CopyCheck()


__all__ = ["check_copies", "check_script"]
