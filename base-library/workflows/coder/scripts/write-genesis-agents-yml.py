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

**Comments are hand-edits too.** A ``safe_load``/``safe_dump`` round-trip preserves every
value and destroys every comment, which on a mature repo is the larger loss — an
``agents.yml`` earns its rationale over time ("this port is taken by the other stack", "these
keys are omitted on purpose"), and none of it is recoverable from the data. So the file is
round-tripped through ``ruamel.yaml``, which carries comments, key order and inline/flow style
through the merge. The file is also left **untouched when the merge changes nothing**, so the
common re-run rewrites nothing at all.

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

import copy
import io
import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.scalarstring import ScalarString


def _yaml(source: str = "") -> YAML:
    """Round-trip loader/dumper: comments, key order and flow style survive the merge.

    ``width`` is set far above any real line because ruamel wraps long scalars at 80 by
    default — which would reflow a hand-written value the merge never touched. The cost is
    the mirror case: a *plain* scalar the author wrapped by hand comes back on one long
    line, because plain multi-line scalars fold to a single string at parse time and their
    break positions are simply not in the loaded document. A block scalar (``>-``) is
    round-tripped byte-for-byte, so that is the shape to reach for when the wrapping of a
    long prose value matters.

    ``source`` is the existing file's text, read for the one thing round-trip mode does
    *not* remember: how far its block sequences are indented. Left at ruamel's default,
    every hand-written ``  - go`` comes back as ``- go`` — a diff touching every list in
    the file, which buries the two lines the merge actually changed.
    """
    y = YAML()  # round-trip mode
    y.preserve_quotes = True
    y.default_flow_style = False
    y.width = 4096
    seq = _sequence_indent(source)
    y.indent(mapping=2, sequence=seq + 2, offset=seq)
    return y


def _sequence_indent(source: str, default: int = 2) -> int:
    """How far ``source`` indents a top-level block-sequence item, or ``default``.

    The shallowest ``- `` in the file is the top-level one; anything deeper is nested and
    would over-indent the whole document if taken as the baseline. A file with no block
    sequence at all (or no file yet) gets ``default``, matching the scaffolded configs.
    """
    indents = [len(line) - len(line.lstrip(" ")) for line in source.splitlines()
               if line.lstrip(" ").startswith("- ") or line.strip() == "-"]
    return min(indents) if indents else default


def _assign_seq(mapping: dict, key: str, merged: list) -> None:
    """Set ``mapping[key]`` to ``merged``, keeping the existing sequence node when possible.

    ``merged`` always starts with the current entries, so the normal case is "append the new
    tail" — done in place so ruamel keeps the node's own style and comments. A flow sequence
    (``service_roots: ["api", "web"]``) rewritten as a fresh list would come back as a block
    list, reflowing a line the merge had no business touching.
    """
    current = mapping.get(key)
    if isinstance(current, list) and list(current) == merged[:len(current)]:
        current.extend(_like(current[0] if current else None, item)
                       for item in merged[len(current):])
        return
    mapping[key] = merged


def _like(sibling, value: str):
    """Return ``value`` quoted the way ``sibling`` is quoted.

    ruamel remembers the quoting of scalars it *loaded*, but a plain ``str`` appended next to
    them dumps bare — leaving ``["api", "web", docs-api]``, which reads as a typo rather than
    as an edit. Mirroring the neighbour keeps the line looking hand-written.
    """
    return type(sibling)(value) if isinstance(sibling, ScalarString) else value


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

    try:
        source = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError as exc:
        emit(agents_yml_note=f"existing agents.yml is unreadable ({exc}); refusing to clobber it")
    yml = _yaml(source)
    existing: dict = {}
    if path.is_file():
        try:
            existing = yml.load(source) or {}
        except (YAMLError, OSError) as exc:
            emit(agents_yml_note=f"existing agents.yml is unreadable ({exc}); refusing to clobber it")
        if not isinstance(existing, dict):
            emit(agents_yml_note="existing agents.yml is not a mapping; refusing to clobber it")

    # Mutate the loaded document in place rather than copying into a plain dict: the comments
    # ride on the loaded mapping, and a `dict(existing)` would drop every one of them.
    had_existing = bool(existing)
    before = copy.deepcopy(existing)
    data = existing
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
            _assign_seq(data, key, merged)

    # In place, again — a `dict(...)` copy here is what would strip the comments a monorepo
    # writes into its own workspace block (which ports are taken, why a key is omitted).
    if not isinstance(data.get("workspace"), dict):
        data["workspace"] = {}
    workspace = data["workspace"]
    workspace.setdefault("type", "mono")
    for key, values in (("service_roots", [service_root] if service_root else []),
                        ("service_markers", markers)):
        if values:
            merged = list(dict.fromkeys([*(workspace.get(key) or []), *values]))
            _assign_seq(workspace, key, merged)

    if data == before and path.is_file():
        note = f"agents.yml for repo '{repo_name}' already carries this service; left untouched"
        logger.info("%s", note)
        emit(agents_yml_written="no", agents_yml_path="agents.yml", agents_yml_note=note)

    buf = io.StringIO()
    yml.dump(data, buf)
    path.write_text(buf.getvalue(), encoding="utf-8")
    verb = "updated" if had_existing else "wrote"
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
