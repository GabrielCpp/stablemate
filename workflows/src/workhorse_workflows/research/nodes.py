"""The research workflow's non-agent work: clone, configure, publish.

Ported from `base-library/workflows/research/scripts/{setup,load_config,publish}.py`.
Three things change and nothing else does:

* the JSON envelope on stdout becomes a **returned model** — a node is a function, so
  its result needs no serialization round-trip to reach the caller;
* the positional `sys.argv` entries become **typed parameters**, checked at the
  callsite by `inspect.signature` rather than by index;
* `sys.exit(1)` becomes `raise WorkflowFailed(...)`, which the driver records as the
  run's terminal state instead of killing the interpreter under it.

The **environment** reads stay verbatim (`AGENT_REPO_DIR`, `REPO_URL`, `REPO_BRANCH`,
`RESEARCH_PROGRAM`, `AGENT_LAUNCH_DIR`, …): they are the operator contract that a
compose file, a Makefile and a container entrypoint all write to, and rewriting them
would break every launcher for no gain.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from workhorse.pyflow import Blueprint, WorkflowFailed
from workhorse.scriptutil import (
    allow_all_directories,
    checkout,
    clone,
    commit_all,
    fetch_reset,
    push_to_origin,
    set_identity,
)
from workhorse_workflows.research.schemas import Program, PublishResult, RepoSetup

blueprint = Blueprint("research")

#: Keys `program.yml` must carry for the gate loop to have anything to run.
REQUIRED = ["code_root"]


# ── setup: get a working tree ───────────────────────────────────────────────


@blueprint.node
def clone_repo(logger: logging.Logger) -> RepoSetup:
    """Check out the repo the program lives in, or adopt the one already there.

    In-place mode wins: when the launcher already put a checkout in front of us
    (`AGENT_REPO_DIR`), cloning would discard uncommitted work and point the run at
    the wrong tree.
    """
    repo_dir_env = os.environ.get("AGENT_REPO_DIR") or os.environ.get("HRNET_REPO_DIR")
    if repo_dir_env:
        allow_all_directories()
        logger.info("in-place mode: using existing repo at %s (no clone)", repo_dir_env)
        return RepoSetup(repo_dir=repo_dir_env)

    # Env before argv so a compose override can redirect the clone source without
    # touching the workflow.
    repo_url = os.environ.get("REPO_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")
    if not repo_url:
        raise WorkflowFailed(
            "no repo to work on: set REPO_URL (or AGENT_REPO_DIR for in-place mode)"
        )
    repo_branch = os.environ.get("REPO_BRANCH") or (
        sys.argv[2] if len(sys.argv) > 2 else "main"
    )

    os.environ.setdefault("GIT_SSH_COMMAND", "ssh -o StrictHostKeyChecking=accept-new")
    # A bind-mounted source repo is owned by the host user; git refuses it as
    # "dubious ownership" without this.
    allow_all_directories()

    workspace = Path("/workspace")
    repo_dir = workspace / Path(repo_url).name.removesuffix(".git")
    workspace.mkdir(parents=True, exist_ok=True)

    if (repo_dir / ".git").is_dir():
        logger.info("repo already present at %s — fetching %s", repo_dir, repo_branch)
        fetch_reset(repo_dir, repo_branch)
    else:
        logger.info("cloning %s (%s) into %s", repo_url, repo_branch, repo_dir)
        clone(repo_url, repo_dir, branch=repo_branch, single_branch=True)

    synced = subprocess.run(
        ["uv", "sync", "--no-sources"],
        cwd=str(repo_dir),
        stdout=sys.stderr,
        stderr=sys.stderr,
        text=True,
        check=False,
    )
    if synced.returncode != 0:
        logger.warning("'uv sync --no-sources' failed; agent must resolve deps")
    return RepoSetup(repo_dir=str(repo_dir))


# ── load_program: which program, and what does it say ───────────────────────


def parse_flat_yaml(text: str, source: str) -> dict[str, str]:
    """Parse a flat `key: value` manifest. No nesting, lists, or multiline values."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()  # drop comments + surrounding space
        if not line:
            continue
        if ":" not in line:
            raise WorkflowFailed(f"{source}: cannot parse line: {raw!r}")
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def slug(program_dir: str) -> str:
    """`specs/alpha/extraction` -> `alpha-extraction`; `research` -> `research`."""
    parts = [p for p in program_dir.split("/") if p not in (".", "", "specs")]
    return "-".join(parts) if parts else program_dir.replace("/", "-")


def _walk_up(start: Path, predicate: Callable[[Path], bool]) -> Path | None:
    """First directory at-or-above `start` (bounded by filesystem root) for which
    `predicate(dir)` is true, or None."""
    cur = start.resolve()
    while True:
        if predicate(cur):
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def launch_dir() -> Path:
    """The directory the run was launched from (the program-selection signal)."""
    return Path(
        os.environ.get("AGENT_LAUNCH_DIR") or os.environ.get("PWD") or os.getcwd()
    ).resolve()


def resolve_repo_root(arg_repo: str) -> Path:
    """Repo root from (in order): explicit arg/env, the launch dir's enclosing
    `.git`, else cwd."""
    explicit = arg_repo or os.environ.get("AGENT_REPO_DIR") or ""
    if explicit:
        return Path(explicit).resolve()
    git_root = _walk_up(launch_dir(), lambda d: (d / ".git").exists())
    return (git_root or Path.cwd()).resolve()


def detect_program_from_launch(repo_root: Path) -> str:
    """Walk up from the launch dir to repo_root; return the repo-relative dir of the
    nearest enclosing `program.yml`, or "" if none is found within the repo."""
    launch = launch_dir()
    try:
        launch.relative_to(repo_root)  # only trust a launch dir inside the repo
    except ValueError:
        return ""

    def has_manifest(d: Path) -> bool:
        if (d / "program.yml").is_file():
            return True
        return d == repo_root  # stop the walk at the repo boundary

    hit = _walk_up(launch, has_manifest)
    if hit is None or not (hit / "program.yml").is_file():
        return ""
    return hit.relative_to(repo_root).as_posix().strip("/")


def read_agents_yaml_program(repo_root: Path) -> str:
    """Top-level `program:` value from the repo's `agents.yml` (the committed default).

    A single top-level key, so a flat scan is enough and no YAML parser is needed."""
    cfg = repo_root / "agents.yml"
    if not cfg.is_file():
        cfg = repo_root / ".agents.yml"  # pre-farrier-1.0 name
    if not cfg.is_file():
        return ""
    for raw in cfg.read_text().splitlines():
        if raw[:1] in (" ", "\t", "#", ""):  # only a top-level (unindented) key
            continue
        line = raw.split("#", 1)[0].rstrip()
        if line.startswith("program:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'").strip("/")
    return ""


def read_pointer(repo_root: Path) -> str:
    pointer = repo_root / ".agents" / "program"
    if not pointer.is_file():
        return ""
    for line in pointer.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            return line.strip("/")
    return ""


@blueprint.node
def load_program(logger: logging.Logger, program: str, repo_dir: str) -> Program:
    """Select a research program and read its manifest into the run's config.

    A "research program" is one folder in the target repo, defined by a flat
    `<program_dir>/program.yml` beside its README ladder — no external registry, and
    nothing per-program in this package. Selection, first match wins:

      1. explicit `program` param / `$RESEARCH_PROGRAM`
      2. the nearest `program.yml` at-or-above the launch dir, bounded by the repo
      3. a top-level `program:` in the repo's `agents.yml` (the committed default)
      4. the legacy `.agents/program` pointer
    """
    explicit = program.strip().strip("/") or os.environ.get(
        "RESEARCH_PROGRAM", ""
    ).strip().strip("/")
    repo_root = resolve_repo_root(repo_dir.strip())

    program_dir = explicit
    selected_by = "explicit"
    if not program_dir:
        program_dir = detect_program_from_launch(repo_root)
        selected_by = "launch-dir"
    if not program_dir:
        program_dir = read_agents_yaml_program(repo_root)
        selected_by = "agents.yml"
    if not program_dir:
        program_dir = read_pointer(repo_root)
        selected_by = "pointer"
    if not program_dir:
        raise WorkflowFailed(
            f"no program selected. Set a top-level `program:` in "
            f"{repo_root / 'agents.yml'}, pass --params '{{\"program\": \"<dir>\"}}', "
            "or launch from inside a program folder (one containing program.yml)."
        )
    logger.info(
        "program %r selected by %s (repo_root=%s, launch_dir=%s)",
        program_dir, selected_by, repo_root, launch_dir(),
    )

    manifest = repo_root / program_dir / "program.yml"
    if not manifest.is_file():
        raise WorkflowFailed(
            f"no program.yml at {program_dir}/program.yml (repo_root={repo_root}). "
            "Create it with at least `code_root: <src dir>`."
        )

    cfg = parse_flat_yaml(manifest.read_text(), str(manifest))
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        raise WorkflowFailed(f"{manifest} missing required keys: {missing}")

    # Preflight: a program the gate loop can actually consume. select_gate reads the
    # README ladder first, so a missing README is fatal; a missing code_root is only a
    # warning (greenfield programs write their first experiment into it).
    if not (repo_root / program_dir / "README.md").is_file():
        raise WorkflowFailed(
            f"{program_dir}/README.md is missing — the gate ladder lives there. "
            f"Scaffold a well-formed program with `make research-new "
            f"DIR={program_dir} CODE_ROOT={cfg['code_root']}`."
        )
    if not (repo_root / cfg["code_root"]).is_dir():
        logger.warning(
            "code_root %r does not exist yet under %s — first experiment will create it.",
            cfg["code_root"], repo_root,
        )

    return Program(
        repo_dir=str(repo_root),
        program=program_dir,
        program_dir=program_dir,
        code_root=cfg["code_root"],
        progress_path=cfg.get("progress_path") or f"{program_dir}/PROGRESS.md",
        result_branch=cfg.get("result_branch") or f"{slug(program_dir)}/auto",
        # Empty → the leads read the README's "North star" section instead.
        goal=cfg.get("goal", ""),
    )


# ── publish: get the gate's work off this machine ───────────────────────────


@blueprint.node
def publish_results(
    logger: logging.Logger,
    repo_dir: str,
    result_branch: str = "research/auto",
    program_dir: str = "",
) -> PublishResult:
    """Commit whatever the gate produced onto the result branch and push it.

    Every failure here is soft: an unpushed branch is still a branch on disk, and
    losing a week of gate work because a remote was unreachable would be the wrong
    trade for an unattended run.
    """
    if not repo_dir:
        raise WorkflowFailed("publish_results needs a repo_dir")

    if program_dir:
        program_label = Path(program_dir).name
    else:
        program_label = (
            result_branch.rsplit("/", 1)[0] if "/" in result_branch else result_branch
        )
    program_label = program_label or result_branch

    set_identity(repo_dir, "Research Agent", "research-agent@local")
    checkout(repo_dir, result_branch, reset=True)
    if not commit_all(repo_dir, f"{program_label}: automated gate update"):
        logger.info("no changes to commit")
        return PublishResult(published=False, result_branch=result_branch)
    if push_to_origin(repo_dir, result_branch, force_with_lease=True):
        return PublishResult(published=True, result_branch=result_branch)
    logger.warning(
        "push failed — edits remain on local branch %s only", result_branch
    )
    return PublishResult(
        published=False, result_branch=result_branch, status="push_failed"
    )


__all__ = ["blueprint", "clone_repo", "load_program", "publish_results"]
