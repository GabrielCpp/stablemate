"""Which research program, and what its manifest says.

Ported from `base-library/workflows/research/scripts/load_config.py`. The selection
ladder is the part worth reading: a program is one folder in the target repo, and
nothing in this package knows any program by name.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.research.nodes._blueprint import blueprint
from workhorse_workflows.research.schemas import Ledger, Program

#: Keys `program.yml` must carry for the gate loop to have anything to run.
REQUIRED = ["code_root"]

#: The machine a measurement is allowed to ask for, and the containment floor it is
#: trusted under. Declared by the program rather than read off the host: a run resumed
#: on a bigger box must not silently accept a job the program was never sized for, and
#: a design that overshoots is rescoped by the scientist rather than escalated to a
#: person. Zero means "unbounded on this axis" — the check only ever refuses a
#: *declared* limit it can compare against.
ENVELOPE_DEFAULTS = {
    "min_containment": "premium",
    "envelope_ram_gb": 0,
    "envelope_cpus": 0,
    "envelope_gpu": "none",
    "envelope_disk_gb": 0,
}

#: The program-scoped counter file, beside `program.yml` and committed with it.
#: Separate from the manifest because the manifest is written by a human and this is
#: written by the loop — an operator resetting a program deletes this, not that.
LEDGER_NAME = "ledger.yml"

#: Statuses that mean a prior run *concluded* the program. Continuing past one is a
#: decision a person makes, not something a relaunch should do silently.
CONCLUDED = ("banked", "reached", "impossible")

LEDGER_HEADER = """\
# Written by the research loop; read at the top of every run.
#
# These counters are program-scoped, not run-scoped: they are what makes
# MAX_EXTENSIONS / MAX_LEAD_REVIEWS bound the *program* rather than one invocation of
# it. Delete this file to reset the program's budget; set `status: active` to
# re-authorize a concluded one (or pass --params '{"reauthorize": true}' once).
"""


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


def _int(cfg: dict[str, str], key: str) -> int:
    """A flat manifest holds strings; an envelope bound is a number or it is nothing."""
    raw = (cfg.get(key) or "").strip()
    if not raw:
        return int(ENVELOPE_DEFAULTS[key])
    try:
        return int(float(raw))
    except ValueError as exc:
        raise WorkflowFailed(f"program.yml: {key} must be a number, got {raw!r}") from exc


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


def launch_dir(launch: str = "") -> Path:
    """The directory the run was launched from (the program-selection signal).

    An argument rather than `AGENT_LAUNCH_DIR`/`PWD`: where the operator stood is an
    input to the selection ladder below, so it travels down from the workflow and is
    visible in the checkpoint. Empty means the process's own working directory.
    """
    return Path(launch or Path.cwd()).resolve()


def resolve_repo_root(arg_repo: str, launch: str = "") -> Path:
    """Repo root from (in order): the explicit argument, the launch dir's enclosing
    `.git`, else cwd."""
    if arg_repo:
        return Path(arg_repo).resolve()
    git_root = _walk_up(launch_dir(launch), lambda d: (d / ".git").exists())
    return (git_root or Path.cwd()).resolve()


def detect_program_from_launch(repo_root: Path, launch: str = "") -> str:
    """Walk up from the launch dir to repo_root; return the repo-relative dir of the
    nearest enclosing `program.yml`, or "" if none is found within the repo."""
    launch_path = launch_dir(launch)
    try:
        launch_path.relative_to(repo_root)  # only trust a launch dir inside the repo
    except ValueError:
        return ""

    def has_manifest(d: Path) -> bool:
        if (d / "program.yml").is_file():
            return True
        return d == repo_root  # stop the walk at the repo boundary

    hit = _walk_up(launch_path, has_manifest)
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


def ledger_path(repo_root: Path, program_dir: str) -> Path:
    return repo_root / program_dir / LEDGER_NAME


def read_ledger(path: Path) -> Ledger:
    """The program's spent counters, or a zeroed ledger when it has none yet.

    Tolerant on the way in: a hand-edited count that is not an integer reads as 0
    rather than failing the run, because a malformed counter must not be the thing
    that stops a program from being worked on.
    """
    if not path.is_file():
        return Ledger(path=str(path))
    cfg = parse_flat_yaml(path.read_text(), str(path))

    def count(key: str) -> int:
        try:
            return max(0, int(cfg.get(key, "0")))
        except ValueError:
            return 0

    return Ledger(
        path=str(path),
        extensions=count("extensions"),
        lead_reviews=count("lead_reviews"),
        status=cfg.get("status") or "active",
    )


@blueprint.node
def record_spend(
    logger: logging.Logger,
    repo_dir: str,
    program_dir: str,
    extensions: int = 0,
    lead_reviews: int = 0,
    status: str = "active",
) -> Ledger:
    """Write the program's spend back to its ledger, for the next run to read.

    Called on every arm that spends one — the two lead-review arms and the extension
    arm — and just before `publish_results`, so the counter travels with the work it
    accounts for rather than living only in this run's checkpoint.
    """
    path = ledger_path(Path(repo_dir), program_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"{LEDGER_HEADER}status: {status}\n"
        f"extensions: {extensions}\n"
        f"lead_reviews: {lead_reviews}\n"
    )
    logger.info(
        "ledger %s: status=%s extensions=%d lead_reviews=%d",
        path, status, extensions, lead_reviews,
    )
    return Ledger(
        path=str(path), extensions=extensions, lead_reviews=lead_reviews, status=status
    )


@blueprint.node
def load_program(
    logger: logging.Logger,
    program: str,
    repo_dir: str,
    launch_dir_path: str = "",
    reauthorize: bool = False,
) -> Program:
    """Select a research program and read its manifest into the run's config.

    A "research program" is one folder in the target repo, defined by a flat
    `<program_dir>/program.yml` beside its README ladder — no external registry, and
    nothing per-program in this package. Selection, first match wins:

      1. the explicit `program` param
      2. the nearest `program.yml` at-or-above the launch dir, bounded by the repo
      3. a top-level `program:` in the repo's `agents.yml` (the committed default)
      4. the legacy `.agents/program` pointer

    Rung 1 lost its `$RESEARCH_PROGRAM` alternative: `program` is already a workflow
    parameter, so the environment spelling was a second way to say the same thing that no
    checkpoint recorded.

    This is also where the program's ledger is read, and where a *concluded* program
    stops: `reauthorize` is the human in the loop that a banked result is worth
    nothing without.
    """
    program_dir = program.strip().strip("/")
    repo_root = resolve_repo_root(repo_dir.strip(), launch_dir_path)

    selected_by = "explicit"
    if not program_dir:
        program_dir = detect_program_from_launch(repo_root, launch_dir_path)
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
        program_dir, selected_by, repo_root, launch_dir(launch_dir_path),
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

    ledger = read_ledger(ledger_path(repo_root, program_dir))
    if ledger.status in CONCLUDED and not reauthorize:
        raise WorkflowFailed(
            f"program {program_dir} is {ledger.status} — a prior run concluded it and "
            f"recorded that in {program_dir}/{LEDGER_NAME}. Read the result first. To "
            "continue it anyway, relaunch with --params '{\"reauthorize\": true}', or "
            f"set `status: active` in {program_dir}/{LEDGER_NAME}."
        )
    if ledger.status in CONCLUDED:
        logger.warning(
            "continuing %s past its %r verdict — reauthorized.", program_dir, ledger.status
        )
    logger.info(
        "program budget already spent: extensions=%d lead_reviews=%d",
        ledger.extensions, ledger.lead_reviews,
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
        min_containment=cfg.get("min_containment") or str(
            ENVELOPE_DEFAULTS["min_containment"]
        ),
        envelope_ram_gb=_int(cfg, "envelope_ram_gb"),
        envelope_cpus=_int(cfg, "envelope_cpus"),
        envelope_gpu=cfg.get("envelope_gpu") or str(ENVELOPE_DEFAULTS["envelope_gpu"]),
        envelope_disk_gb=_int(cfg, "envelope_disk_gb"),
        extensions_spent=ledger.extensions,
        lead_reviews_spent=ledger.lead_reviews,
        # Reauthorizing does not un-conclude the program on disk; the loop writes the
        # status back itself on the arm that spends. Carrying `active` here keeps the
        # in-run reading of `self.ctx.status` about *this* run.
        status="active" if reauthorize else ledger.status,
    )



__all__ = ["ENVELOPE_DEFAULTS", "load_program", "read_ledger", "record_spend"]
