#!/usr/bin/env python3
"""Emit one backlog bullet per assessed (uncovered) baseline surface."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import yaml


BEGIN = "<!-- parity-surveyor:begin — generated; do not edit inside this fence -->"
END = "<!-- parity-surveyor:end -->"
HEADING = "## Legacy surfaces missing from the new app"
FRONT_MATTER = re.compile(r"^\s*---\s*\n(.*?)\n---", re.S)


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def replace_section(text: str, section: str) -> str:
    begin, end = text.find(BEGIN), text.find(END)
    if begin != -1 and end > begin:
        return text[:begin] + section + text[end + len(END):]
    prefix = text.rstrip() + "\n\n" if text.strip() else "# Backlog\n\n"
    return f"{prefix}{HEADING}\n\n{section}\n"


def main() -> None:
    root = Path(os.environ.get("AGENT_REPO_DIR", Path.cwd())).resolve()
    inventory_rel, findings_rel, backlog_rel, manifest_rel = sys.argv[1:5]
    try:
        inventory = json.loads((root / inventory_rel).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"emit_ok": "no", "emit_errors": str(exc), "bullet_count": 0,
                          "emit_note": ""}))
        return

    bullets: list[str] = []
    manifest_units: list[dict[str, object]] = []
    suppressed = 0
    for unit in inventory.get("units", []):
        uid = str(unit.get("id", ""))
        record_path = root / findings_rel / f"{slug(uid)}.md"
        match = FRONT_MATTER.match(record_path.read_text(encoding="utf-8"))
        record = yaml.safe_load(match.group(1)) if match else {}
        status = str(record.get("status", ""))
        owner = str(record.get("existing_owner", "")).strip()
        bullet_id = f"legacy-parity-{unit.get('area')}-{unit.get('slug')}"
        emitted = status == "assessed" and not owner
        if emitted:
            finding = (record.get("findings") or [{}])[0]
            description = " ".join(str(finding.get("description", "")).split())
            bullets.append(f"- [{bullet_id}] {description}")
        elif status == "assessed" and owner:
            suppressed += 1
        manifest_units.append({
            "id": uid,
            "path": unit.get("path", ""),
            "status": status,
            "existingOwner": owner,
            "bullet": bullet_id if emitted else "",
        })

    section = "\n".join([BEGIN, *bullets, END])
    backlog_path = root / backlog_rel
    backlog_path.parent.mkdir(parents=True, exist_ok=True)
    existing = backlog_path.read_text(encoding="utf-8") if backlog_path.is_file() else ""
    backlog_path.write_text(replace_section(existing, section), encoding="utf-8")
    manifest_path = root / manifest_rel
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({
        "version": 1,
        "generatedBy": "parity-surveyor",
        "baseline": inventory.get("baseline", ""),
        "units": manifest_units,
    }, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "emit_ok": "yes",
        "emit_errors": "",
        "bullet_count": len(bullets),
        "emit_note": f"wrote {len(bullets)} missing-surface bullet(s); suppressed {suppressed} already-owned surface(s)",
    }))


if __name__ == "__main__":
    main()
