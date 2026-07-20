#!/usr/bin/env python3
"""Run the stack's native init tooling, then assert it produced the service marker.

This is the node that makes a scaffolded folder into a *service*. Scaffolds seed a directory
and a ``.gitignore``; they do not produce ``go.mod`` / ``package.json`` / ``pubspec.yaml``, and
those marker files are precisely what ``validate-plan-context.py`` looks for when deciding
whether the planner may target a service. So genesis shells out to the real tool —
``go mod init``, ``npm create react-router``, ``flutter create`` — rather than templating a
fake skeleton. Using the native tool means the layout matches whatever that ecosystem
currently generates, which is not something a library snapshot can stay correct about.

The command and the marker are **flow parameters, not built-in knowledge**. Genesis must carry
no stack knowledge (``check_public.py``: no base workflow may depend on the overlay, and the
stack packs live there). ``farrier``'s pack schema merges exactly five set-valued keys with no
slot for an init command, so parameters are the honest place for this until the shape has been
proven across all four stacks — inventing a pack ``genesis:`` block before then is how you get
a schema you regret.

Idempotent: if the marker is already present the command is skipped, because `go mod init` and
friends fail or clobber on re-run.

Args:
    argv[1]  target_dir   : absolute path to the repo
    argv[2]  service_root : repo-relative dir to init in (created if absent)
    argv[3]  init_cmd     : shell command to run there ('' ⇒ skip, marker must already exist)
    argv[4]  marker       : filename that proves the init worked (e.g. "go.mod")

Outputs JSON: {"skeleton_ok": "yes"|"no", "skeleton_note": "<line>", "marker_path": "<rel>"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


def emit(**kwargs) -> NoReturn:
    payload = {"skeleton_ok": "no", "skeleton_note": "", "marker_path": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def _arg(idx: int, default: str = "") -> str:
    return (sys.argv[idx].strip() if len(sys.argv) > idx and sys.argv[idx] else "") or default


def main(logger: logging.Logger) -> None:
    target_arg = _arg(1)
    service_root = _arg(2)
    init_cmd = _arg(3)
    marker = _arg(4)

    if not target_arg:
        emit(skeleton_note="no target_dir was provided")
    target = Path(target_arg)
    if not target.is_dir():
        emit(skeleton_note=f"target {target} is not a directory")

    service_dir = (target / service_root) if service_root else target
    service_dir.mkdir(parents=True, exist_ok=True)
    marker_rel = f"{service_root}/{marker}".lstrip("/") if service_root else marker

    if marker and (service_dir / marker).exists():
        logger.info("%s already present — skipping init", marker_rel)
        emit(skeleton_ok="yes", marker_path=marker_rel,
             skeleton_note=f"{marker_rel} already present; native init skipped (idempotent re-run)")

    if not init_cmd:
        emit(skeleton_note=(
            f"no init_cmd was provided and {marker_rel or '<no marker>'} does not exist — "
            f"pass the stack's native init command as a flow param, e.g. "
            f"--params '{{\"init_cmd\":\"go mod init example.com/api\",\"marker\":\"go.mod\"}}'"))

    logger.info("running init in %s: %s", service_dir, init_cmd)
    result = subprocess.run(init_cmd, cwd=str(service_dir), shell=True, capture_output=True,
                            text=True, check=False, timeout=900)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        emit(skeleton_note=f"init_cmd failed ({init_cmd}): {detail}")

    # The command exiting 0 is not proof it made a service — some generators write into a
    # subdirectory, or no-op when they think one already exists. The marker is the proof.
    if marker and not (service_dir / marker).exists():
        emit(skeleton_note=(
            f"init_cmd succeeded but {marker_rel} was not created. The service is not real to "
            f"validate-plan-context.py without it — check whether the tool wrote into a "
            f"subdirectory of {service_dir}, and adjust service_root or init_cmd."))

    note = f"native init ran in {service_root or '.'}; {marker_rel} present"
    logger.info("%s", note)
    emit(skeleton_ok="yes", marker_path=marker_rel, skeleton_note=note)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("init-genesis-skeleton"))
