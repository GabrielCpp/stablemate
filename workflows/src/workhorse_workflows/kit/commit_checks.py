"""The commit checks a repo declares, run over the paths a workflow is about to commit, so a workflow's commit meets what an agent's commit meets."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from git import Repo
from git.exc import GitError

from workhorse_workflows.kit.git import open_repo, stage_paths
from workhorse_workflows.kit.tools import run_tool

COMMAND_ENV = "AGENT_COMMIT_COMMAND"
CWD_ENV = "AGENT_COMMIT_CWD"


def _declared(root: Path) -> list[tuple[str, float]]:
    """The ``(command, budget)`` lines ``farrier checks`` lists for *root*. Nothing when farrier is absent or lists none."""
    try:
        listed = run_tool(["farrier", "checks", "--repo", str(root)], root)
    except OSError:
        return []
    if listed.returncode != 0:
        return []
    checks: list[tuple[str, float]] = []
    for line in listed.stdout.splitlines():
        command, _, budget = line.partition("\t")
        if command.strip():
            checks.append((command.strip(), float(budget) if budget.strip() else 0.0))
    return checks


def _has_staged(repo: Repo, pathspecs: tuple[str, ...]) -> bool:
    return bool(repo.git.diff("--cached", "--name-only", "--", *pathspecs).strip())


def unstage_paths(root: Path, pathspecs: tuple[str, ...]) -> None:
    """Leave *pathspecs* unstaged, as they were before the checks staged them."""
    try:
        repo = open_repo(root)
        repo.git.reset("-q", "--", *pathspecs)
    except GitError:
        return


def declared_checks_failure(root: Path, message: str, pathspecs: tuple[str, ...]) -> str:
    """Run the repo's declared commit checks over *pathspecs* as staged, and return what every failing one said, in order, each under the line that names its command. Empty when all pass.

    A failing check leaves *pathspecs* unstaged, as a refused commit does.
    """
    checks = _declared(root)
    if not checks or not pathspecs:
        return ""
    try:
        repo = open_repo(root)
        stage_paths(repo, *pathspecs)
        if not _has_staged(repo, pathspecs):
            return ""
    except GitError as failed:
        return str(failed)
    env = {COMMAND_ENV: shlex.join(["git", "commit", "-m", message]), CWD_ENV: str(root)}
    failures: list[str] = []
    for command, budget in checks:
        try:
            ran = run_tool(
                [*shlex.split(command), *pathspecs],
                cwd=root,
                env=env,
                timeout=max(budget * 10, 60.0),
            )
        except (OSError, subprocess.TimeoutExpired) as unrunnable:
            failures.append(f"commit check `{command}` could not run: {unrunnable}")
        else:
            if ran.returncode != 0:
                failures.append(f"commit check `{command}` refused the commit:\n{(ran.stderr or ran.stdout).strip()}")
    if failures:
        repo.git.reset("-q", "--", *pathspecs)
    return "\n\n".join(failures)
