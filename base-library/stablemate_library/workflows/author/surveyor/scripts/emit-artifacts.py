#!/usr/bin/env python3
"""Emit the author workflow's input contract from the validated partition.

The surveyor's whole output is author's *existing* input, so author runs unchanged
(epic mode, ``coverage_mode: "full"``) and its own gates prove nothing was dropped.
Two artifacts:

1. **Generated backlog bullets** — one ``[survey-<cluster-id>]`` bullet per cluster,
   written into a marker-fenced section of the backlog file so re-emitting is
   idempotent (the section is replaced wholesale; anything outside the markers —
   a human-curated backlog, coder's ``## Filed by coder`` section — is untouched).
   Grouping/ordering hints ride in the bullet text; the cluster id in the bullet is
   the traceability hop the author's ``sourceBullet`` chain extends downward:
   **unit → finding → backlog bullet → seed → story**.

2. **The unit-level manifest** — the role ``cfg.surface_manifest`` plays in author
   today, with a survey-produced list instead of feature docs. Every unit carries the
   bullet ids that cover it, so author's ``verify-surface-coverage.py`` (full mode)
   can assert mechanical coverage: a unit with work is covered while its bullet (or
   the seed that consumed it) is present; a ``clean``/accepted-``blocked`` unit
   carries no bullets and demands no coverage.

Runs after ``validate-partition.py`` passed, so the partition is trusted here.

Stdlib + PyYAML (available in the system interpreter).

Args:
    argv[1]  partition     : repo-relative path to partition.yaml
    argv[2]  inventory     : repo-relative path to inventory.json
    argv[3]  backlog       : repo-relative backlog markdown to write bullets into
    argv[4]  unit_manifest : repo-relative path for the emitted manifest JSON

Outputs JSON: {"emit_ok": "yes"|"no", "emit_errors": "<lines>",
               "bullet_count": <int>, "emit_note": "<summary>"}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with the system interpreter here
    yaml = None

SECTION_BEGIN = "<!-- surveyor:begin — generated; do not edit inside this fence -->"
SECTION_END = "<!-- surveyor:end -->"
SECTION_HEADING = "## Survey findings"


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: str, errors: list[str] | str = "", count: int = 0, note: str = "") -> None:
    msg = errors if isinstance(errors, str) else "\n".join(errors)
    print(json.dumps({"emit_ok": ok, "emit_errors": msg, "bullet_count": count,
                      "emit_note": note}))
    sys.exit(0)


def bullet_for(cluster: dict) -> str:
    cid = str(cluster["id"])
    title = str(cluster.get("title", "")).strip()
    strategy = str(cluster.get("strategy", ""))
    pattern = str(cluster.get("remediation_pattern", ""))
    n = len(cluster.get("units") or [])
    hints = [f"pattern: {pattern}"]
    hints.append(f"{n} unit(s), {strategy}" +
                 (" checklist — keep as ONE story with a per-unit checklist" if strategy == "mechanical" else ""))
    notes = str(cluster.get("notes") or "").strip().replace("\n", " ")
    if notes:
        hints.append(notes)
    return f"- [survey-{cid}] {title} ({'; '.join(hints)})"


def replace_section(text: str, section: str) -> str:
    """Replace the marker-fenced survey section, or append one if absent."""
    begin, end = text.find(SECTION_BEGIN), text.find(SECTION_END)
    if begin != -1 and end != -1 and end > begin:
        return text[:begin] + section + text[end + len(SECTION_END):]
    body = text.rstrip("\n")
    prefix = (body + "\n\n") if body else "# Backlog\n\n"
    return prefix + SECTION_HEADING + "\n\n" + section + "\n"


def main() -> None:
    part_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/survey/partition.yaml"
    inv_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/survey/inventory.json"
    backlog_rel = (sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else "") or "docs/backlog.md"
    manifest_rel = (sys.argv[4].strip() if len(sys.argv) > 4 and sys.argv[4] else "") or "docs/survey/unit-manifest.json"

    root = find_repo_root()
    if yaml is None:
        emit("no", ["PyYAML is required to parse the partition file but is unavailable"])
    try:
        part = yaml.safe_load((root / part_rel).read_text(encoding="utf-8"))
        clusters = part.get("clusters") or []
        assert isinstance(clusters, list) and clusters
    except (OSError, yaml.YAMLError, AttributeError, AssertionError):
        emit("no", [f"partition at {part_rel} could not be read — run the partition gate first"])
    try:
        units = json.loads((root / inv_rel).read_text(encoding="utf-8")).get("units") or []
    except (OSError, json.JSONDecodeError, ValueError):
        emit("no", [f"inventory at {inv_rel} could not be read"])

    # ── Backlog bullets: one per cluster, in the marker-fenced generated section ───────
    ordered = sorted((c for c in clusters if isinstance(c, dict)),
                     key=lambda c: (c.get("order", 10**6), str(c.get("id", ""))))
    lines = [SECTION_BEGIN] + [bullet_for(c) for c in ordered] + [SECTION_END]
    section = "\n".join(lines)

    backlog_path = root / backlog_rel
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    existing = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    backlog_path.write_text(replace_section(existing, section), encoding="utf-8")

    # ── Unit manifest: every unit + the bullets that cover it ──────────────────────────
    bullets_by_unit: dict[str, list[str]] = {}
    clusters_by_unit: dict[str, list[str]] = {}
    for c in ordered:
        cid = str(c.get("id", ""))
        for uid in c.get("units") or []:
            bullets_by_unit.setdefault(str(uid), []).append(f"survey-{cid}")
            clusters_by_unit.setdefault(str(uid), []).append(cid)

    manifest_units = []
    for u in units:
        if not isinstance(u, dict):
            continue
        uid = str(u.get("id", ""))
        manifest_units.append({
            "id": uid,
            "path": str(u.get("path", uid)),
            "kind": str(u.get("kind", "")),
            "status": str(u.get("status", "")),
            "bullets": bullets_by_unit.get(uid, []),
            "clusters": clusters_by_unit.get(uid, []),
        })

    manifest_path = root / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "version": 1,
        "generatedBy": "surveyor",
        "inventory": inv_rel,
        "units": manifest_units,
    }, indent=2) + "\n", encoding="utf-8")

    emit("yes", count=len(ordered),
         note=f"wrote {len(ordered)} bullet(s) into {backlog_rel} and "
              f"{len(manifest_units)} unit(s) into {manifest_rel}")


if __name__ == "__main__":
    main()
