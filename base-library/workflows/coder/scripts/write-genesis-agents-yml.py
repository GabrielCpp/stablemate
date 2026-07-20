#!/usr/bin/env python3
"""Write the genesis repo's ``agents.yml`` — packs, scaffolds, and the ``workspace:`` block.

**Genesis carries zero stack knowledge.** Every stack-specific value (which packs to install,
which scaffold to render, the service root, the service markers) arrives as a flow parameter
and is written through verbatim. That is not incidental: ``scripts/check_public.py`` asserts
no base workflow may depend on the private overlay, and the stack skills/packs live there. A
base workflow that knew ``go`` meant ``main.go`` would be a base workflow that knows the
overlay's contents. This mirrors how ``requirements.py`` "knows no tool's name".

The ``workspace:`` block is what lets the planner target the service at all — it is where
``service_roots`` and ``service_markers`` come from, and ``resolve_workspace`` merges it into
the repo record that ``validate-plan-context.py`` reads.

Existing files are **merged, not overwritten**: on a re-run (``target_state: existing``) the
repo may carry hand-edits, and clobbering them would make genesis unsafe to re-run — which is
the whole point of the detect/decide nodes upstream.

Args:
    argv[1]  target_dir   : absolute path to the repo
    argv[2]  service      : logical service name (also the workspace repo key)
    argv[3]  packs        : comma-separated farrier pack ids (stack knowledge, passed in)
    argv[4]  service_root : repo-relative dir the service lives in (e.g. "api")
    argv[5]  markers      : comma-separated service marker filenames (e.g. "go.mod,main.go")
    argv[6]  workflows    : comma-separated workflows to register (default "coder")
    argv[7]  scaffolds    : comma-separated "<scaffold-id>[:<dir>]" pairs — only the ids are
                            written here. `farrier scaffold <id>` refuses to render an id that
                            is not enabled in this list, so install_farrier's scaffold step
                            silently renders nothing unless this node declares them first.
    argv[8]  assistants   : comma-separated agent backends to enable (default "claude").
                            `farrier install` hard-exits with no `agents:` key at all.

Outputs JSON: {"agents_yml_written": "yes"|"no", "agents_yml_path": "<rel>",
               "agents_yml_note": "<line>"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

import yaml


def emit(**kwargs) -> NoReturn:
    payload = {"agents_yml_written": "no", "agents_yml_path": "", "agents_yml_note": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _arg(idx: int, default: str = "") -> str:
    return (sys.argv[idx].strip() if len(sys.argv) > idx and sys.argv[idx] else "") or default


def main(logger: logging.Logger) -> None:
    target_arg = _arg(1)
    service = _arg(2)
    packs = csv(_arg(3))
    service_root = _arg(4)
    markers = csv(_arg(5))
    workflows = csv(_arg(6, "coder"))
    # "<id>:<dir>" pairs in, bare ids out — the dir is install_farrier's business.
    scaffolds = [entry.partition(":")[0].strip() for entry in csv(_arg(7))]
    scaffolds = [s for s in scaffolds if s]
    assistants = csv(_arg(8, "claude"))

    if not target_arg:
        emit(agents_yml_note="no target_dir was provided")
    target = Path(target_arg)
    if not target.is_dir():
        emit(agents_yml_note=f"target {target} is not a directory")

    # The repo's name is its directory name — NOT the service's. One monorepo holds many
    # services, and two things key off this: `resolve_workspace` keys the workspace on it
    # (so `validate-plan-context.py` resolves services under it), and farrier derives the
    # generated-skill prefix from it. Using the first surface's service name produced a
    # workspace keyed on "api" and 49 skills named `api-flutter-*`.
    repo_name = target.name
    path = target / "agents.yml"

    existing: dict = {}
    if path.is_file():
        try:
            existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError) as exc:
            emit(agents_yml_note=f"existing agents.yml is unreadable ({exc}); refusing to clobber it")
        if not isinstance(existing, dict):
            emit(agents_yml_note="existing agents.yml is not a mapping; refusing to clobber it")

    data = dict(existing)
    data.setdefault("repo", {})
    if isinstance(data["repo"], dict):
        data["repo"].setdefault("name", repo_name)

    # `farrier install` hard-exits with "No agents selected in config" when this key is
    # absent, so omitting it made install fail outright — which then surfaced downstream as
    # an empty instructions map and sent validate_genesis into a repair loop for something
    # entirely deterministic. setdefault, not assignment: a repo that has already chosen its
    # assistants keeps that choice across a config-refresh re-run.
    data.setdefault("agents", {name: name in assistants
                               for name in ("claude", "codex", "copilot")})

    # Union rather than replace: a re-run must not drop packs or workflows a human added.
    for key, values in (("packs", packs), ("workflows", workflows), ("scaffolds", scaffolds)):
        if values:
            merged = list(dict.fromkeys([*(data.get(key) or []), *values]))
            data[key] = merged

    workspace = dict(data.get("workspace") or {})
    workspace.setdefault("type", "mono")
    if service_root:
        workspace["service_roots"] = list(dict.fromkeys(
            [*(workspace.get("service_roots") or []), service_root]))
    if markers:
        workspace["service_markers"] = list(dict.fromkeys(
            [*(workspace.get("service_markers") or []), *markers]))
    data["workspace"] = workspace

    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
                    encoding="utf-8")
    verb = "updated" if existing else "wrote"
    note = (f"{verb} agents.yml for repo '{repo_name}'"
            f"{f", service '{service}'" if service else ''} "
            f"(packs: {', '.join(packs) or '<none>'}; "
            f"scaffolds: {', '.join(scaffolds) or '<none>'}; "
            f"agents: {', '.join(sorted(k for k, v in data['agents'].items() if v)) or '<none>'}; "
            f"service_roots: {', '.join(workspace.get('service_roots') or []) or '<none>'}; "
            f"service_markers: {', '.join(workspace.get('service_markers') or []) or '<none>'})")
    logger.info("%s", note)
    emit(agents_yml_written="yes", agents_yml_path="agents.yml", agents_yml_note=note)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("write-genesis-agents-yml"))
