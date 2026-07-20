#!/usr/bin/env python3
"""Resolve the genesis target directory and report whether it is already a live repo.

Genesis is re-run constantly during setup iteration, so it has to be safe to re-run. This
node is what makes that true: it classifies the target before anything mutates it, and the
flow routes an already-initialised repo to config-refresh-only instead of re-scaffolding
over the top of real work.

Three states, deliberately distinguished:

* ``absent``   — the directory does not exist (or is empty). Full genesis.
* ``partial``  — the directory exists with content but has no ``agents.yml``. Full genesis,
                 but nothing is deleted; existing files are left exactly as they are.
* ``existing`` — an ``agents.yml`` is already there. Config-refresh only; never re-scaffold.

**Repo state and service state are tracked separately**, because a monorepo grows one
service at a time. Keying the skeleton step on the *repo* would mean the second run into an
existing monorepo (adding ``web`` beside ``api``) sees ``existing`` and skips the skeleton
entirely, so no second service could ever be created. ``service_state`` keys on that
service's own marker file instead: the repo may be long-established while this service does
not exist yet.

Args:
    argv[1]  target       : path to the repo to create (absolute, or relative to CWD)
    argv[2]  service      : logical service name (also the workspace repo key)
    argv[3]  service_root : repo-relative dir this service lives in (e.g. "api")
    argv[4]  marker       : file proving the service exists (e.g. "go.mod")

Outputs JSON: {"target_ok": "yes"|"no", "target_dir": "<abs>",
               "target_state": "absent"|"partial"|"existing",
               "service_state": "absent"|"existing", "service": "<name>",
               "genesis_note": "<human line>"}

``target_ok: "no"`` (no target given) routes straight to the fail terminal. Without that the
whole flow runs against an empty path — every script no-ops with a note, and the run still
reaches the conventions agent, which burns a model call to discover there is nothing there.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import NoReturn


def emit(**kwargs) -> NoReturn:
    payload = {"target_ok": "yes", "target_dir": "", "target_state": "absent",
               "service_state": "absent", "service": "", "genesis_note": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def classify(target: Path) -> str:
    if (target / "agents.yml").is_file():
        return "existing"
    if not target.exists():
        return "absent"
    # An existing-but-empty dir is indistinguishable from absent for our purposes, and
    # treating it as `partial` would route a fresh `mkdir` away from full genesis.
    if not any(target.iterdir()):
        return "absent"
    return "partial"


def main(logger: logging.Logger) -> None:
    target_arg = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    service = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    service_root = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else ""
    marker = sys.argv[4].strip() if len(sys.argv) > 4 and sys.argv[4] else ""

    if not target_arg:
        logger.error("no target directory was provided")
        emit(target_ok="no", target_state="absent",
             genesis_note="no target directory was provided; "
                          "pass --params '{\"target\":\"<path>\", ...}'")

    target = Path(target_arg).expanduser().resolve()
    state = classify(target)

    # Keyed on this service's marker, independent of repo state — see the module docstring.
    service_dir = (target / service_root) if service_root else target
    service_state = "existing" if (marker and (service_dir / marker).is_file()) else "absent"

    notes = {
        "absent": f"{target} does not exist yet — running full genesis",
        "partial": (f"{target} exists with content but has no agents.yml — running full genesis; "
                    f"nothing already there will be removed"),
        "existing": (f"{target} already has an agents.yml — refreshing config only, "
                     f"not re-scaffolding"),
    }
    note = notes[state]
    if service_root:
        note += (f"; service '{service or service_root}' at {service_root}/ is {service_state}"
                 f" (marker: {marker or '<none declared>'})")
    logger.info("%s", note)
    emit(target_ok="yes", target_dir=str(target), target_state=state,
         service_state=service_state, service=service, genesis_note=note)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("resolve-genesis-target"))
