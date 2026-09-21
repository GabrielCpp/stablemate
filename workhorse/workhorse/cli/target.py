"""Which run dir an operator command means — shared by `control` and `inbox`."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from workhorse.rundir import find_latest_resumable, resolve_run_dir

GROOM_URL_VAR = "GROOM_URL"
DEFAULT_GROOM_URL = "http://127.0.0.1:8787"
_GROOM_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class LiveLookup:
    """What groom said about a run id: the dir it serves, or why there is none."""

    run_dir: Path | None
    note: str


LiveLookupFn = Callable[[str, str, str], LiveLookup]


def groom_live_run(run_id: str, workflow: str, url: str) -> LiveLookup:
    """Ask groom's ``/api/live`` for the run dir behind ``run_id``."""
    query = urllib.parse.urlencode({"run": run_id})
    try:
        with urllib.request.urlopen(f"{url}/api/live?{query}", timeout=_GROOM_TIMEOUT_S) as resp:
            rows = json.loads(resp.read())
    except (OSError, ValueError):
        return LiveLookup(None, f"groom at {url} not reachable")
    if not isinstance(rows, list):
        return LiveLookup(None, f"groom at {url} answered with something other than run rows")
    candidates = [
        Path(row["run_dir"])
        for row in rows
        if isinstance(row, dict)
        and row.get("workflow") == workflow
        and isinstance(row.get("run_dir"), str)
        and row["run_dir"]
    ]
    here = [path for path in candidates if path.is_dir()]
    if len(here) == 1:
        return LiveLookup(here[0], f"resolved {run_id!r} via groom: {here[0]}")
    if candidates and not here:
        return LiveLookup(
            None,
            f"groom at {url} knows live run {run_id!r} for workflow {workflow!r}, but its "
            f"run dir is not on this machine: {', '.join(str(p) for p in candidates)}",
        )
    if len(here) > 1:
        return LiveLookup(
            None,
            f"groom at {url} knows {len(here)} live runs named {run_id!r} for workflow "
            f"{workflow!r}; pass the run dir instead: {', '.join(str(p) for p in here)}",
        )
    return LiveLookup(None, f"groom at {url} knows no live run {run_id!r} for workflow {workflow!r}")


def resolve_target(
    spec: str | None,
    runs_dir: Path,
    workflow_name: str,
    *,
    live: LiveLookupFn = groom_live_run,
) -> Path:
    """The run dir to write into — named, or the one unfinished run there is."""
    if spec is not None:
        resolved = resolve_run_dir(spec, runs_dir, workflow_name)
        if resolved is not None:
            return resolved
        answer = live(spec, workflow_name, os.environ.get(GROOM_URL_VAR) or DEFAULT_GROOM_URL)
        if answer.run_dir is not None:
            print(answer.note, file=sys.stderr)
            return answer.run_dir
        print(
            f"error: no run dir for {spec!r} (looked under {runs_dir})\n  {answer.note}",
            file=sys.stderr,
        )
        sys.exit(1)

    latest = find_latest_resumable(runs_dir)
    if latest is None:
        print(
            f"error: no unfinished run found under {runs_dir} — name one with --run",
            file=sys.stderr,
        )
        sys.exit(1)
    return latest
