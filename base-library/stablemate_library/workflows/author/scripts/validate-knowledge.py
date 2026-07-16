#!/usr/bin/env python3
"""Hard, deterministic validator for a surface knowledge record.

The knowledge record is the durable, accumulating, two-sided (old/new) source of derived
truth for one surface — its components and their data sources — built by
``gather-surface-knowledge.md`` and consumed by write-story / plan / implement / QA.

The record **describes** a surface; it does not carry a worklist. What a story should build
comes from its epic's seeds.

This validator keeps the gather honest so downstream stages can trust the record:

  - the record file exists and is valid JSON
  - it conforms to ``knowledge.schema.json`` (structural shape, required fields, enums)
  - no component leaves its data source unknown/guessed: each component carries a
    ``dataSource.kind`` (or the component is recorded with an explicit ``"unknown"`` that
    is flagged) — an untraced data source must be an ``openGaps`` prerequisite, not a guess

Advisory by design: it returns ``knowledge_ok`` + ``knowledge_errors`` so the workflow can
log/branch without hard-crashing a best-effort observation (a partly-unreachable surface is
legitimate and recorded via ``openGaps`` + a ``blocked`` gather status).

No ``jsonschema``: runs under the system ``python3``, not the uv venv. The schema documents the
enum/required vocab; structural checks are hand-rolled. The record itself is now a Markdown file
with a YAML **front-matter** block carrying the structured fields (PyYAML is available in the
system interpreter); legacy ``.json`` records are still parsed for back-compat.

Args:
    argv[1]  record_path : repo-relative path to the knowledge record (``.md`` with YAML
             front-matter, or a legacy ``.json`` record)

Outputs JSON: {"knowledge_ok": "yes"|"no", "knowledge_errors": "<newline-joined>"}
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with the system interpreter here
    yaml = None

_FRONT_MATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)


def load_record(text: str) -> dict:
    """Parse a knowledge record from raw file text.

    A record is a Markdown file whose leading ``---`` fenced block is YAML front-matter holding
    the structured fields (the prose body below it is human-only and not parsed). A legacy raw
    ``.json`` record is parsed directly. Raises ``ValueError`` on a malformed record.
    """
    if text.lstrip().startswith("---"):
        m = _FRONT_MATTER_RE.match(text)
        if not m:
            raise ValueError("YAML front-matter block is not closed by a second `---` fence")
        if yaml is None:
            raise ValueError("PyYAML is required to parse front-matter records but is unavailable")
        # A malformed front-matter block raises yaml.YAMLError (e.g. ParserError/ScannerError),
        # which is NOT a ValueError — re-raise it as one so the caller's handler turns it into a
        # `knowledge_ok: no` finding (a fixable defect) instead of crashing the whole workflow.
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML front-matter is not valid: {exc}") from exc
        return data if isinstance(data, dict) else {}
    return json.loads(text)

DATASOURCE_KINDS = {"api", "computed", "static", "legacy"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: bool, errors: list[str]) -> None:
    print(json.dumps({
        "knowledge_ok": "yes" if ok else "no",
        "knowledge_errors": "\n".join(errors),
    }))


def check_component(where: str, idx: int, comp: object, errors: list[str]) -> None:
    if not isinstance(comp, dict):
        errors.append(f"{where}[{idx}] is not an object")
        return
    name = comp.get("name")
    if not (isinstance(name, str) and name.strip()):
        errors.append(f"{where}[{idx}] missing non-empty `name`")
    ds = comp.get("dataSource")
    # A component with no traced data source is exactly what this check exists to prevent.
    if not isinstance(ds, dict) or not str(ds.get("kind") or "").strip():
        errors.append(
            f"{where}[{idx}] ({name or '?'}) has no dataSource.kind — trace where its data "
            f"comes from, or record it in openGaps with a prerequisite (do not guess)"
        )
    elif ds.get("kind") not in DATASOURCE_KINDS:
        errors.append(
            f"{where}[{idx}] ({name or '?'}) dataSource.kind '{ds.get('kind')}' not one of "
            f"{sorted(DATASOURCE_KINDS)}"
        )


def main() -> None:
    record_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    if not record_rel:
        emit(False, ["no record_path supplied"])
        return

    root = find_repo_root()
    record_path = (root / record_rel).resolve()
    if not record_path.is_file():
        emit(False, [f"knowledge record missing at {record_path}"])
        return

    try:
        record = load_record(record_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError) as exc:
        emit(False, [f"record could not be parsed: {exc}"])
        return

    errors: list[str] = []

    if not isinstance(record, dict):
        emit(False, ["record root is not a JSON object"])
        return

    surface = record.get("surface")
    if not (isinstance(surface, str) and surface.strip()):
        errors.append("missing non-empty `surface`")

    for side in ("old", "new"):
        inv = record.get(side)
        if inv is None:
            continue
        if not isinstance(inv, list):
            errors.append(f"`{side}` must be an array of components")
            continue
        for i, comp in enumerate(inv):
            check_component(side, i, comp, errors)

    # A record that documented no components at all usually means the surface was never
    # actually read — flag it (advisory).
    if not (record.get("old") or record.get("new") or record.get("openGaps")):
        errors.append(
            "record documents no components and records no openGaps — a surface with nothing "
            "described and no blocked prerequisite is suspicious; confirm the surface was read"
        )

    emit(not errors, errors)


if __name__ == "__main__":
    main()
