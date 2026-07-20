#!/usr/bin/env python3
"""Assert the genesis repo satisfies every precondition the main loop assumes.

Genesis's postcondition **is** the main loop's precondition, so the two are checked with one
shared implementation (``service_contract.service_problems``, also used by
``validate-plan-context.py``). Without that sharing the two drift apart silently and the only
symptom is a confusing planner rejection several stages later.

What is checked, and why each one earns its place:

* **ostler binds to this repo.** The one genuinely silent failure in the whole flow.
  ``ostler.model.find_root`` walks *up* for ``.git`` / ``docs/`` / ``ostler.yml`` /
  ``agents.yml``; before ``git init`` a fresh directory matches none of them and ostler binds
  to an ancestor repo without erroring — ids allocated from the parent's registry, docs written
  into the parent's tree. Nothing downstream would notice, which is why it is asserted here.
* **``.git`` with at least one commit.** An unborn HEAD has nothing for a branch to point at,
  and ``branch-author.py`` cuts a branch almost immediately.
* **The service marker exists.** The shared assertion above; this is what makes the service
  real to the planner rather than just a folder.
* **``.agents/agents-context.json`` has a non-empty ``instructions`` map.** This is how
  ``resolve-impl-context.py`` resolves skills for a service. Empty means every skill silently
  resolves to nothing and implementation runs unskilled — a vacuous success, not a crash.
* **``docs/epics/`` exists.** ostler infers its graph profile from this directory, and only the
  ``full`` profile runs the structural doctor checks the author workflow's coverage gate
  depends on. Absent, epic-coverage validation short-circuits and reports success having
  checked nothing.
* **``docs/backlog.md`` exists.** ``load-config.py`` hard-exits without it.
* **A ``make lint`` target.** Reported as a warning, not an error: the lint gate degrades to a
  skip without one, so this is a legibility problem rather than a broken repo.

Args:
    argv[1]  target_dir   : absolute path to the repo genesis created
    argv[2]  service_root : repo-relative service dir (e.g. "api")
    argv[3]  markers      : comma-separated service marker filenames

Outputs JSON: {"genesis_valid": "yes"|"no", "genesis_errors": "<newline-joined>",
               "genesis_warnings": "<newline-joined>"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

from service_contract import service_problems


def emit(valid: bool, errors: list[str], warnings: list[str]) -> NoReturn:
    print(json.dumps({
        "genesis_valid": "yes" if valid else "no",
        "genesis_errors": "\n".join(errors),
        "genesis_warnings": "\n".join(warnings),
    }))
    sys.exit(0)


def _arg(idx: int, default: str = "") -> str:
    return (sys.argv[idx].strip() if len(sys.argv) > idx and sys.argv[idx] else "") or default


def ostler_root(target: Path) -> Path | None:
    """Where ostler *actually* binds when run from ``target`` — not where we hope it does."""
    try:
        from ostler.model import find_root
    except ImportError:
        return None
    try:
        return Path(find_root(target)).resolve()
    except (OSError, ValueError, RuntimeError):
        return None


def has_commit(target: Path) -> bool:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(target),
                            capture_output=True, text=True, check=False, timeout=15)
    return result.returncode == 0 and bool(result.stdout.strip())


def has_lint_target(target: Path) -> bool:
    makefile = next((target / name for name in ("Makefile", "makefile")
                     if (target / name).is_file()), None)
    if makefile is None:
        return False
    return any(line.startswith("lint:") or line.startswith("lint ")
               for line in makefile.read_text(encoding="utf-8").splitlines())


def main(logger: logging.Logger) -> None:
    target_arg = _arg(1)
    service_root = _arg(2)
    markers = [m.strip() for m in _arg(3).split(",") if m.strip()]

    errors: list[str] = []
    warnings: list[str] = []

    if not target_arg:
        emit(False, ["no target_dir was provided"], [])
    target = Path(target_arg).resolve()
    if not target.is_dir():
        emit(False, [f"target {target} is not a directory"], [])

    # ── git ──
    if not (target / ".git").exists():
        errors.append(f"no .git at {target} — ostler will bind to an ancestor repo, and "
                      f"branch-author.py cannot cut a branch")
    elif not has_commit(target):
        errors.append(f"{target} has an unborn HEAD (no commit) — there is nothing for a "
                      f"branch to point at")

    # ── ostler binds HERE, not to an ancestor ──
    bound = ostler_root(target)
    if bound is None:
        warnings.append("could not import ostler to verify graph binding — skipped that check")
    elif bound != target:
        errors.append(
            f"ostler binds to {bound}, not {target}. Ids would be allocated from that repo's "
            f"registry and docs written into its tree, silently. This is the failure mode "
            f"git_init exists to prevent — check that node ran before any ostler call."
        )

    # ── the service is real to the planner ──
    if service_root:
        errors.extend(service_problems(target / service_root, markers,
                                       f"{target.name}::{service_root}"))

    # ── skills actually resolve ──
    ctx_path = target / ".agents" / "agents-context.json"
    if not ctx_path.is_file():
        errors.append(f"no {ctx_path.relative_to(target)} — farrier install did not run, so "
                      f"resolve-impl-context.py will resolve every skill to nothing")
    else:
        try:
            instructions = (json.loads(ctx_path.read_text(encoding="utf-8")) or {}).get("instructions")
        except (OSError, json.JSONDecodeError, ValueError):
            instructions = None
        if not instructions:
            errors.append(
                f"{ctx_path.relative_to(target)} has an empty 'instructions' map — the "
                f"implementation stage would run with no skills and still report success"
            )

    # ── the docs ground author and coder both stand on ──
    if not (target / "docs" / "epics").is_dir():
        errors.append("no docs/epics/ — ostler infers the 'exploration' profile without it, "
                      "and epic-coverage validation then short-circuits and asserts nothing")
    if not (target / "docs" / "backlog.md").is_file():
        errors.append("no docs/backlog.md — the author workflow's load-config.py hard-exits")

    # ── advisory ──
    if not has_lint_target(target):
        warnings.append("no `lint` target in a Makefile — the coder workflow's lint gate will "
                        "skip rather than fail, so lint findings would go unreported")

    if errors:
        logger.warning("genesis validation failed with %d error(s)", len(errors))
    else:
        logger.info("genesis validation passed%s",
                    f" with {len(warnings)} warning(s)" if warnings else "")
    emit(not errors, errors, warnings)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-genesis"))
