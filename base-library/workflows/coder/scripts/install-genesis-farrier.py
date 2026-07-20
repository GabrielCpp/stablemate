#!/usr/bin/env python3
"""Run farrier against the genesis repo: install the packs, then render the scaffolds.

Two farrier calls, in order:

1. ``farrier install --repo <target>`` — reads the ``agents.yml`` the previous node wrote and
   renders the declared packs into the repo's adapters, producing
   ``.agents/agents-context.json``. That file's ``instructions`` map is what
   ``resolve-impl-context.py`` reads to decide which skills apply to a service; without it
   every skill silently resolves to nothing and the implementation stage runs unskilled.
2. ``farrier scaffold <id> --param dir=<root>`` per scaffold — seeds the conventional folder
   and its ``.gitignore``.

Scaffolds are deliberately thin (a folder and a ``.gitignore``, no marker file), so this node
establishes *convention and hygiene* only. The thing that makes the service real to
``validate-plan-context.py`` is the marker file, and that comes from native init tooling in
``init-genesis-skeleton.py``. The two steps are complementary, not redundant.

Scaffold ids arrive as parameters for the same reason packs do — genesis carries no stack
knowledge.

Args:
    argv[1]  target_dir   : absolute path to the repo
    argv[2]  scaffolds    : comma-separated "<scaffold-id>:<dir>" pairs
                            (e.g. "shared-docs:docs,go-service:api"); ":<dir>" optional
    argv[3]  skip_install : "yes" to skip `farrier install` (scaffolds only)

Outputs JSON: {"farrier_ok": "yes"|"no", "farrier_note": "<lines>",
               "scaffolds_rendered": "<comma-separated ids>"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


def emit(**kwargs) -> NoReturn:
    payload = {"farrier_ok": "no", "farrier_note": "", "scaffolds_rendered": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True,
                          check=False, timeout=300)


def _arg(idx: int, default: str = "") -> str:
    return (sys.argv[idx].strip() if len(sys.argv) > idx and sys.argv[idx] else "") or default


def main(logger: logging.Logger) -> None:
    target_arg = _arg(1)
    scaffold_spec = _arg(2)
    skip_install = _arg(3).lower() in ("yes", "true", "1")

    if not target_arg:
        emit(farrier_note="no target_dir was provided")
    target = Path(target_arg)
    if not target.is_dir():
        emit(farrier_note=f"target {target} is not a directory")

    notes: list[str] = []

    if not skip_install:
        result = run(["farrier", "install", "--repo", str(target)], target)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            emit(farrier_note=f"farrier install failed: {detail}")
        notes.append("farrier install: adapters + .agents/agents-context.json rendered")

    rendered: list[str] = []
    for entry in (part.strip() for part in scaffold_spec.split(",") if part.strip()):
        scaffold_id, _, dir_param = entry.partition(":")
        scaffold_id = scaffold_id.strip()
        args = ["farrier", "scaffold", scaffold_id, "--repo", str(target)]
        if dir_param.strip():
            args += ["--param", f"dir={dir_param.strip()}"]
        result = run(args, target)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            emit(farrier_ok="no", scaffolds_rendered=",".join(rendered),
                 farrier_note="\n".join([*notes, f"scaffold '{scaffold_id}' failed: {detail}"]))
        rendered.append(scaffold_id)
        notes.append(f"scaffold '{scaffold_id}' rendered at '{dir_param.strip() or '<default>'}'")

    logger.info("farrier ok: %d scaffold(s) rendered", len(rendered))
    emit(farrier_ok="yes", scaffolds_rendered=",".join(rendered), farrier_note="\n".join(notes))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("install-genesis-farrier"))
