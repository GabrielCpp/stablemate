#!/usr/bin/env python3
"""Load an in-repo research program manifest and expose it as `cfg`.

The single, program-agnostic research workflow runs this right after `setup`, so
the target repo is already checked out. A "research program" is a folder in that
repo (1 folder = 1 program), with its definition co-located as a tiny flat manifest
`<program_dir>/program.yml` — no external JSON registry, no per-program edits to
this library.

Program selection (first match wins):

  1. Explicit  — `argv[1]` (from `--params '{"program": "specs/<dir>"}'`) or the
     `$RESEARCH_PROGRAM` env var. Highest precedence; overrides everything.
  2. Launch dir — the program is picked *relative to the directory the run was
     launched from*. Starting at `$AGENT_LAUNCH_DIR` (else `$PWD`, else cwd) we walk
     UP toward the repo root and select the nearest ancestor that contains a
     `program.yml`. So `cd specs/SMCNv3 && <launch>` (or pointing AGENT_LAUNCH_DIR at
     a program folder) selects that program with no flags.
  3. agents.yml — the committed default: a top-level `program:` key in the repo's
     `agents.yml` (the farrier toolkit config). This is the normal way to pin the
     active program for the repo.
  4. Pointer    — the repo's committed `.agents/program` file (legacy fallback).

Repo root is `argv[2]` (setup_result.repo_dir) or `$AGENT_REPO_DIR`, else the first
ancestor of the launch dir containing a `.git`, else cwd. Repo-level concerns
(repo_url/repo_branch) are NOT part of a program — `setup` owns cloning/in-place
selection — so they are deliberately absent from `cfg`.

Manifest (`program.yml`) — flat `key: value`, '#' comments, no nesting/lists:
  code_root: src/mypkg                 # required
  progress_path: specs/.../PROGRESS.md # optional, default <program_dir>/PROGRESS.md
  result_branch: my-program/auto       # optional, default <slug>/auto
  goal: <one-line standing goal>       # optional; else the lead reads README's North star

Stdlib-only: scripts run under the system `python3`, not the uv venv (no pyyaml).

Outputs JSON: {"cfg": { program_dir, code_root, progress_path, result_branch,
                       goal, program }}
"""
import json
import logging
import os
import sys
from pathlib import Path

REQUIRED = ["code_root"]


def parse_flat_yaml(text: str, source: str) -> dict[str, str]:
    """Parse a flat `key: value` manifest. No nesting, lists, or multiline values."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()  # drop comments + surrounding space
        if not line:
            continue
        if ":" not in line:
            sys.exit(f"[load_config] {source}: cannot parse line: {raw!r}")
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def slug(program_dir: str) -> str:
    """`specs/alpha/extraction` -> `alpha-extraction`; `research` -> `research`."""
    parts = [p for p in program_dir.split("/") if p not in (".", "", "specs")]
    return "-".join(parts) if parts else program_dir.replace("/", "-")


def _walk_up(start: Path, predicate) -> Path | None:
    """First directory at-or-above `start` (bounded by filesystem root) for which
    `predicate(dir)` is true, or None."""
    cur = start.resolve()
    while True:
        if predicate(cur):
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def resolve_repo_root(arg_repo: str) -> Path:
    """Repo root from (in order): explicit arg/env, the launch dir's enclosing
    `.git`, else cwd."""
    explicit = arg_repo or os.environ.get("AGENT_REPO_DIR") or ""
    if explicit:
        return Path(explicit).resolve()
    launch = launch_dir()
    git_root = _walk_up(launch, lambda d: (d / ".git").exists())
    return (git_root or Path.cwd()).resolve()


def launch_dir() -> Path:
    """The directory the run was launched from (the program-selection signal)."""
    return Path(
        os.environ.get("AGENT_LAUNCH_DIR") or os.environ.get("PWD") or os.getcwd()
    ).resolve()


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

    Stdlib-only scan for a single top-level key — no pyyaml, no nested parsing needed."""
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


def main(logger: logging.Logger) -> None:
    explicit = (sys.argv[1].strip() if len(sys.argv) > 1 else "").strip("/") or (
        os.environ.get("RESEARCH_PROGRAM", "").strip().strip("/")
    )
    repo_root = resolve_repo_root(sys.argv[2].strip() if len(sys.argv) > 2 else "")

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
        logger.error(
            "no program selected. Set a top-level `program:` in %s, pass "
            "--params '{\"program\": \"<dir>\"}', or launch from inside a program "
            "folder (one containing program.yml).", repo_root / "agents.yml",
        )
        sys.exit(1)
    logger.info(
        "program %r selected by %s (repo_root=%s, launch_dir=%s)",
        program_dir, selected_by, repo_root, launch_dir(),
    )

    manifest = repo_root / program_dir / "program.yml"
    if not manifest.is_file():
        logger.error(
            "no program.yml at %s/program.yml (repo_root=%s). Create it with at "
            "least `code_root: <src dir>`.", program_dir, repo_root,
        )
        sys.exit(1)

    cfg = parse_flat_yaml(manifest.read_text(), str(manifest))
    missing = [k for k in REQUIRED if not cfg.get(k)]
    if missing:
        logger.error("%s missing required keys: %s", manifest, missing)
        sys.exit(1)

    # Preflight: a program the gate-loop can actually consume. select_gate reads the
    # README ladder first, so a missing README is fatal; a missing code_root is only a
    # warning (greenfield programs write their first experiment into it).
    readme = repo_root / program_dir / "README.md"
    if not readme.is_file():
        logger.error(
            "%s/README.md is missing — the gate ladder lives there. Scaffold a "
            "well-formed program with `make research-new DIR=%s CODE_ROOT=%s`.",
            program_dir, program_dir, cfg["code_root"],
        )
        sys.exit(1)
    if not (repo_root / cfg["code_root"]).is_dir():
        logger.warning(
            "code_root %r does not exist yet under %s — first experiment will create it.",
            cfg["code_root"], repo_root,
        )

    cfg["program_dir"] = program_dir
    cfg.setdefault("progress_path", f"{program_dir}/PROGRESS.md")
    cfg.setdefault("result_branch", f"{slug(program_dir)}/auto")
    cfg.setdefault("goal", "")  # empty → leads read the README's "North star" section
    cfg["program"] = program_dir

    print(json.dumps({"cfg": cfg}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("load_config"))
