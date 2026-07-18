#!/usr/bin/env python3
"""Fail-closed conformance and direct-grounding gate for one story's OKF update."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from ostler import Ostler

from workhorse.scriptutil import find_docs_root


def _emit(status: str, notes: str, **details: object) -> None:
    print(
        json.dumps(
            {
                "documentation_gate": {
                    "status": status,
                    "notes": notes,
                    **details,
                }
            }
        )
    )


def _context_path(docs_root: Path, spec_dir: str) -> Path:
    spec = Path(spec_dir)
    if not spec.is_absolute():
        spec = docs_root / spec
    return spec / "qa-okf-context.json"


def _directly_grounded_paths(packet: dict) -> tuple[set[str], set[str]]:
    exact: set[str] = set()
    files: set[str] = set()
    for item in packet.get("directNodes", []):
        if not isinstance(item, dict):
            continue
        for reason in item.get("reasons", []):
            if not isinstance(reason, dict):
                continue
            kind = reason.get("kind")
            ref = str(reason.get("ref", ""))
            if kind == "changed-code":
                exact.add(ref.strip().strip("`, "))
            elif kind == "file-owner":
                files.add(ref)
    return exact, files


def _affected_doc_nodes(packet: dict, author_nodes: list[str]) -> set[str]:
    nodes = {
        str(item.get("node", ""))
        for item in packet.get("directNodes", [])
        if isinstance(item, dict)
        and any(
            isinstance(reason, dict)
            and reason.get("kind") in {"changed-code", "file-owner", "surface-owner"}
            for reason in item.get("reasons", [])
        )
    }
    nodes.update(author_nodes)
    return {node for node in nodes if node}


def _finding_affects_nodes(okf: Ostler, finding: dict, affected_nodes: set[str]) -> bool:
    path = str(finding.get("path", ""))
    candidates = {node for node in affected_nodes if node.partition("#")[0] == path}
    if not candidates:
        return False
    if path in candidates:
        return True
    line = int(finding.get("line") or 0)
    if not line:
        return True
    try:
        nodes = [
            node
            for node in okf.graph.ui_nodes
            if node.path.relative_to(okf.graph.root).as_posix() == path and node.line <= line
        ]
    except (OSError, ValueError, RuntimeError):
        return True
    if not nodes:
        return True
    owner = max(nodes, key=lambda node: node.line)
    while owner is not None:
        if owner.id in candidates:
            return True
        owner = okf.graph.find_ui_node(owner.parent) if owner.parent else None
    return False


def main(logger: logging.Logger) -> None:
    docs_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    spec_dir = sys.argv[2] if len(sys.argv) > 2 else ""
    author_status = sys.argv[3] if len(sys.argv) > 3 else "blocked"
    build_status = sys.argv[4] if len(sys.argv) > 4 else "invalid"
    validation_status = sys.argv[5] if len(sys.argv) > 5 else "invalid"
    context_mode = sys.argv[6] if len(sys.argv) > 6 else "local"
    author_nodes_json = sys.argv[7] if len(sys.argv) > 7 else "[]"
    docs_root = Path(find_docs_root(docs_arg))

    try:
        loaded_nodes = json.loads(author_nodes_json)
        author_nodes = [str(node) for node in loaded_nodes] if isinstance(loaded_nodes, list) else []
    except json.JSONDecodeError:
        author_nodes = []

    problems: list[str] = []
    if author_status not in {"documented", "not_required"}:
        problems.append(f"documentation author status is {author_status!r}")
    if author_status == "documented" and not author_nodes:
        problems.append("documentation author did not identify affected OKF nodes")
    if context_mode == "local" and build_status != "passed":
        problems.append("diff-to-OKF context generation did not pass")
    if context_mode == "local" and validation_status != "passed":
        problems.append("diff-to-OKF context validation did not pass")

    packet: dict = {}
    if context_mode == "local":
        packet_path = _context_path(docs_root, spec_dir)
        try:
            loaded = json.loads(packet_path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("context is not an object")
            packet = loaded
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            problems.append(f"cannot read {packet_path}: {exc}")

    exactly_grounded, file_grounded = _directly_grounded_paths(packet)
    surface_only: list[str] = []
    for change in packet.get("changedCode", []):
        if not isinstance(change, dict):
            continue
        candidates = {
            str(change.get("path", "")),
            str(change.get("basePath", "")),
            str(change.get("headPath", "")),
        } - {""}
        base_path = str(change.get("basePath", ""))
        head_path = str(change.get("headPath", ""))
        base_symbols = set(change.get("baseSymbols", []))
        head_symbols = set(change.get("headSymbols", []))
        symbols = base_symbols | head_symbols
        required_refs = {
            *(f"{base_path}::{symbol}" for symbol in base_symbols if base_path),
            *(f"{head_path}::{symbol}" for symbol in head_symbols if head_path),
        }
        grounded = (
            required_refs.issubset(exactly_grounded)
            if symbols
            else not candidates.isdisjoint(
                {ref.partition("::")[0] for ref in exactly_grounded} | file_grounded
            )
        )
        if not grounded:
            surface_only.append(str(change.get("path", "<unknown>")))
    if surface_only:
        problems.append(
            "changed production units have only broad surface ownership: "
            + ", ".join(sorted(surface_only))
        )

    try:
        okf = Ostler(docs_root)
        report = okf.doctor()
    except (OSError, ValueError, RuntimeError) as exc:
        report = {}
        problems.append(f"ostler doctor could not run: {exc}")
    affected_doc_nodes = _affected_doc_nodes(packet, author_nodes)
    doctor_errors = [
        finding
        for finding in report.get("findings", [])
        if isinstance(finding, dict)
        and finding.get("severity") == "error"
        and not (
            context_mode == "semantic"
            and finding.get("code") in {"dangling-code-ref", "missing-code-symbol"}
        )
        and _finding_affects_nodes(okf, finding, affected_doc_nodes)
    ]
    if doctor_errors:
        pointers = [
            f"{item.get('path') or item.get('ref') or '<graph>'}:"
            f"{item.get('line') or 0} [{item.get('code', '?')}] {item.get('message', '')}"
            for item in doctor_errors
        ]
        problems.append("ostler doctor errors: " + " | ".join(pointers))

    if problems:
        notes = "; ".join(problems)
        logger.warning("story documentation invalid: %s", notes)
        _emit(
            "invalid",
            notes,
            changed_code_count=len(packet.get("changedCode", [])),
            doctor_error_count=len(doctor_errors),
        )
        return

    notes = (
        f"Affected documentation is conformant; {len(packet.get('changedCode', []))} changed "
        "production unit(s) have direct OKF grounding."
    )
    logger.info(notes)
    _emit(
        "passed",
        notes,
        changed_code_count=len(packet.get("changedCode", [])),
        doctor_error_count=0,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("verify-story-documentation"))
