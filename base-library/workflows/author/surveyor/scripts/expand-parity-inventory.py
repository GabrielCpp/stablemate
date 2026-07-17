#!/usr/bin/env python3
"""Freeze one survey unit per baseline surface from a JSON inventory."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def emit(ok: str, errors: str = "", count: int = 0, note: str = "") -> None:
    print(json.dumps({"expand_ok": ok, "expand_errors": errors, "unit_count": count,
                      "inventory_note": note}))


def main() -> None:
    root = Path(os.environ.get("AGENT_REPO_DIR", Path.cwd())).resolve()
    baseline_rel = sys.argv[1]
    inventory_rel = sys.argv[2]
    output = root / inventory_rel
    if output.is_file():
        try:
            units = json.loads(output.read_text(encoding="utf-8"))["units"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            emit("no", f"frozen inventory is invalid: {exc}")
            return
        emit("yes", count=len(units), note=f"inventory frozen at {inventory_rel}")
        return
    try:
        baseline = json.loads((root / baseline_rel).read_text(encoding="utf-8"))
        entries = baseline["entries"]
        if not isinstance(entries, list):
            raise TypeError("entries is not a list")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        emit("no", f"baseline inventory is invalid: {exc}")
        return

    base_dir = Path(baseline_rel).parent
    units = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("rewriteSurface") is True:
            continue
        area, slug = str(entry.get("area", "")).strip(), str(entry.get("slug", "")).strip()
        if not area or not slug:
            emit("no", "every baseline entry must have non-empty area and slug")
            return
        unit_id = f"legacy/{area}/{slug}"
        if unit_id in seen:
            emit("no", f"duplicate baseline surface: {unit_id}")
            return
        seen.add(unit_id)
        units.append({
            "id": unit_id,
            "path": (base_dir / area / f"{slug}.md").as_posix(),
            "kind": "legacy-surface",
            "status": "pending",
            "area": area,
            "slug": slug,
            "title": str(entry.get("title", slug)),
            "route": str(entry.get("route", "")),
        })
    if not units:
        emit("no", "baseline inventory contains no non-rewrite surfaces")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "version": 1,
        "baseline": baseline_rel,
        "units": units,
    }, indent=2) + "\n", encoding="utf-8")
    emit("yes", count=len(units), note=f"froze {len(units)} baseline surfaces")


if __name__ == "__main__":
    main()
