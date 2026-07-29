"""Which research program, and what its manifest says.

Ported from `base-library/workflows/research/scripts/load_config.py`. The selection
ladder is the part worth reading: a program is one folder in the target repo, and
nothing in this package knows any program by name.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import Program

#: Keys `program.yml` must carry for the gate loop to have anything to run.
REQUIRED = ["code_root"]


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



__all__ = ["load_program"]
