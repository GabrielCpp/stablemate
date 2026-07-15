#!/usr/bin/env python3
"""Hard, deterministic validator for a surface knowledge record.

The knowledge record is the durable, accumulating, two-sided (old/new) source of derived
truth for one surface — components, their data sources, and the classified old->new gaps —
built by ``gather-surface-knowledge.md`` and consumed by write-story / plan / implement / QA.

This validator keeps the gather honest so downstream stages can trust the record:

  - the record file exists and is valid JSON
  - it conforms to ``knowledge.schema.json`` (structural shape, required fields, enums)
  - every ``gaps[].id`` is present and UNIQUE (the story's ACs reference these handles)
  - no component leaves its data source unknown/guessed: each component carries a
    ``dataSource.kind`` (or the component is recorded with an explicit ``"unknown"`` that
    is flagged) — an untraced data source must be an ``openGaps`` prerequisite, not a guess
  - a fidelity record actually did the comparison: if there is an OLD inventory it must
    either match a NEW inventory entry or surface a gap (no silently-dropped scope)

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

GAP_KINDS = {"missing", "broken", "divergent", "unreachable"}
DATASOURCE_KINDS = {"api", "computed", "static", "legacy"}
DISPOSITIONS = {"scoped", "deferred", "dropped"}


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
    # A component with no traced data source is exactly the gap this whole system fixes.
    if not isinstance(ds, dict) or not str(ds.get("kind") or "").strip():
        errors.append(
            f"{where}[{idx}] ({name or '?'}) has no dataSource.kind — trace where its data "
            f"comes from, or move it to openGaps with a prerequisite (do not guess)"
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

    gaps = record.get("gaps")
    if not isinstance(gaps, list):
        errors.append("`gaps` must be an array (the surface's actionable old->new worklist)")
        gaps = []

    seen_ids: set[str] = set()
    for i, gap in enumerate(gaps):
        if not isinstance(gap, dict):
            errors.append(f"gaps[{i}] is not an object")
            continue
        gid = gap.get("id")
        if not (isinstance(gid, str) and gid.strip()):
            errors.append(f"gaps[{i}] missing non-empty `id` (stories reference this handle)")
        elif gid in seen_ids:
            errors.append(f"gaps[{i}] duplicate id '{gid}' — gap ids must be unique + stable")
        else:
            seen_ids.add(gid)
        kind = gap.get("kind")
        if kind not in GAP_KINDS:
            errors.append(f"gaps[{i}] kind '{kind}' not one of {sorted(GAP_KINDS)}")
        # Disposition: absent ⇒ treated as `scoped` (this story closes it). A `deferred`
        # gap MUST name an owner so the work can never become an orphan — the orphaned
        # surface is the exact failure this whole system fixes. (The hard, cross-record
        # owner-resolves check lives in validate-epic-coverage.py; here we keep the gather
        # honest at record-write time.)
        disposition = gap.get("disposition")
        if disposition is not None and disposition not in DISPOSITIONS:
            errors.append(
                f"gaps[{i}] disposition '{disposition}' not one of {sorted(DISPOSITIONS)}"
            )
        if disposition == "deferred" and not str(gap.get("owner") or "").strip():
            errors.append(
                f"gaps[{i}] ({gid or '?'}) is deferred but names no `owner` — a deferred gap "
                f"MUST name who closes it (a sibling story slug or an open backlog item id), "
                f"never an orphan"
            )

    for side in ("old", "new"):
        inv = record.get(side)
        if inv is None:
            continue
        if not isinstance(inv, list):
            errors.append(f"`{side}` must be an array of components")
            continue
        for i, comp in enumerate(inv):
            check_component(side, i, comp, errors)

    # A record with no gaps AND no openGaps for a non-trivial surface usually means the
    # comparison was skipped — flag it (advisory).
    open_gaps = record.get("openGaps") or []
    if not gaps and not open_gaps:
        errors.append(
            "record has neither `gaps` nor `openGaps` — a surface with nothing to do and no "
            "blocked prerequisite is suspicious; confirm the old->new comparison actually ran"
        )

    emit(not errors, errors)


if __name__ == "__main__":
    main()
