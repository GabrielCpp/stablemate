"""Which run dir an operator command means — shared by `control` and `inbox`.

Both commands take the same `--run` / `--runs-dir` pair and mean the same thing by it,
so the resolution lives once: a named run is looked up by every name the operator
already has for it (its id, its dir name, a path), and with no name at all the target
is the one unfinished run there is.
"""
from __future__ import annotations

import sys
from pathlib import Path

from workhorse.rundir import find_latest_resumable, resolve_run_dir


def resolve_target(spec: str | None, runs_dir: Path, workflow_name: str) -> Path:
    """The run dir to write into — named, or the one unfinished run there is.

    Defaulting is worth having and worth bounding: an operator reloading the run they
    are watching should not have to retype an id they never chose, but a *wrong* guess
    would send the request to a run nobody asked about. So the default is the same
    "newest run that never reached a terminal" that `--resume-latest` means, and it is
    printed back, since a reload is only cheap when it lands on the intended run.
    """
    if spec is not None:
        resolved = resolve_run_dir(spec, runs_dir, workflow_name)
        if resolved is None:
            print(
                f"error: no run dir for {spec!r} (looked under {runs_dir})",
                file=sys.stderr,
            )
            sys.exit(1)
        return resolved

    latest = find_latest_resumable(runs_dir)
    if latest is None:
        print(
            f"error: no unfinished run found under {runs_dir} — name one with --run",
            file=sys.stderr,
        )
        sys.exit(1)
    return latest
