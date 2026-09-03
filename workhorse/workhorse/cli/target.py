"""Which run dir an operator command means — shared by `control` and `inbox`.

Both commands take the same `--run` / `--runs-dir` pair and mean the same thing by it,
so the resolution lives once: a named run is looked up by every name the operator
already has for it (its id, its dir name, a path), and with no name at all the target
is the one unfinished run there is.

A name that matches nothing locally is then asked of groom. The ids an operator holds
mostly come from `groom status` or the dashboard, and the run dirs behind them live in
the *target* repo, not under the cwd's `./.agents/runs` — so from anywhere but that
repo a bare id used to fail as "no run dir", which reads as a missing run and sends
people searching the disk for it. groom already indexes every live run with its
`run_dir`; asking it turns that failure into a resolution, and when groom cannot
answer, the error says so instead of implying the run is gone.
"""
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

#: groom's serve URL — the same variable groom's own CLI reads, and the same port
#: `workhorse.otel` exports to by default.
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
    """Ask groom's ``/api/live`` for the run dir behind ``run_id``.

    Only a row for *this* workflow whose ``run_dir`` exists on this machine counts: the
    id namespace is per workflow, and a dir groom sees inside a container is not one
    this process can open a socket in. Anything else — groom down, an unparseable
    answer, no row, two rows — is a miss with a note, never an exception: the lookup is
    a convenience on top of the local resolution, and must not turn a local error into
    a network one.
    """
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
    """The run dir to write into — named, or the one unfinished run there is.

    Defaulting is worth having and worth bounding: an operator reloading the run they
    are watching should not have to retype an id they never chose, but a *wrong* guess
    would send the request to a run nobody asked about. So the default is the same
    "newest run that never reached a terminal" that `--resume-latest` means, and it is
    printed back, since a reload is only cheap when it lands on the intended run.

    A named run is resolved locally first, then through groom; the groom hit is printed
    back for the same reason the default is.
    """
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
