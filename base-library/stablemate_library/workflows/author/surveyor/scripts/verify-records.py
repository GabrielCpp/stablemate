#!/usr/bin/env python3
"""Deterministic survey-coverage gate: every frozen unit accounted for, no silent shrinkage.

Runs when the per-unit loop finds nothing pending. The loop's empty select IS the
coverage proof — this gate makes the claim auditable and catches the ways it can rot:

- a unit still ``pending`` (an operator re-pended it, or a hand-edited inventory) —
  the loop must re-enter, not proceed;
- a unit whose finding record is missing, unparseable, or structurally invalid, or
  whose record ``status`` disagrees with the inventory entry (the two files are one
  claim — they must agree);
- a ``blocked`` unit with no ``disposition: accepted`` in its record — an OPEN gap.
  The operator (or auto-resolver) either fixes the precondition and flips the unit
  back to ``pending`` (the loop re-assesses it) or records the accepted disposition
  with a reason (the gap is owned, not orphaned);
- **reconcile-style shrinkage** (the ``reconcile-artifacts.py`` pattern): a unit
  present in the last *committed* inventory that is absent now, with no split lineage
  (children extending its path) — a frozen-list drop is a regression, never a clean
  re-derivation. Fail-open: no git / no committed baseline → that check skips.

Always exits 0; status is in the JSON, not the exit code.

Stdlib + PyYAML (available in the system interpreter).

Args:
    argv[1]  inventory    : repo-relative path to inventory.json
    argv[2]  findings_dir : repo-relative findings root
    argv[3]  baseline ref (default HEAD) : git ref the shrinkage check compares against

Outputs JSON: {"verify_ok": "yes"|"no"|"skip", "verify_errors": "<lines>",
               "verify_report": "<one line>"}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with the system interpreter here
    yaml = None

_FRONT_MATTER_RE = re.compile(r"^\s*---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)
_PATTERN_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RECORD_STATUSES = {"assessed", "clean", "blocked"}
UNIT_STATUSES = {"pending", "assessed", "clean", "blocked"}
EFFORTS = {"trivial", "small", "substantial"}


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(ok: str, errors: list[str] | str = "", report: str = "") -> None:
    msg = errors if isinstance(errors, str) else "\n".join(errors)
    print(json.dumps({"verify_ok": ok, "verify_errors": msg, "verify_report": report}))
    sys.exit(0)


def record_slug(unit_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", unit_id.lower()).strip("-")


def load_record(text: str) -> dict:
    """Parse a record's YAML front-matter (same contract as validate-record.py)."""
    if not text.lstrip().startswith("---"):
        raise ValueError("record has no leading `---` YAML front-matter block")
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        raise ValueError("YAML front-matter block is not closed by a second `---` fence")
    if yaml is None:
        raise ValueError("PyYAML is required to parse finding records but is unavailable")
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        raise ValueError(f"YAML front-matter is not valid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("front-matter must be a mapping")
    return data


def record_errors(record: dict, unit_id: str) -> list[str]:
    """Compact structural re-check (validate-record.py's rules; kept in sync by the tests)."""
    errors: list[str] = []
    if record.get("type") != "survey-finding":
        errors.append("`type` must be `survey-finding`")
    if str(record.get("unit") or "").strip() != unit_id:
        errors.append(f"`unit` does not match inventory id '{unit_id}'")
    status = record.get("status")
    if status not in RECORD_STATUSES:
        errors.append(f"`status` '{status}' not one of {sorted(RECORD_STATUSES)}")
    findings = record.get("findings") or []
    if not isinstance(findings, list):
        errors.append("`findings` must be a list")
        findings = []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            errors.append(f"findings[{i}] is not a mapping")
            continue
        if not str(f.get("description") or "").strip():
            errors.append(f"findings[{i}] missing `description`")
        if not _PATTERN_SLUG_RE.match(str(f.get("remediation_pattern") or "")):
            errors.append(f"findings[{i}] `remediation_pattern` must be a kebab-case slug")
        if f.get("effort") not in EFFORTS:
            errors.append(f"findings[{i}] effort '{f.get('effort')}' not one of {sorted(EFFORTS)}")
        if not str(f.get("evidence") or "").strip():
            errors.append(f"findings[{i}] missing `evidence`")
    if status == "assessed" and not findings:
        errors.append("status `assessed` with no findings — should be `clean`")
    if status == "clean" and findings:
        errors.append("status `clean` with findings — contradiction")
    if status == "blocked" and not (isinstance(record.get("openGaps"), list) and record.get("openGaps")):
        errors.append("status `blocked` with empty `openGaps`")
    return errors


def git_show(root: Path, ref: str, relpath: str) -> str | None:
    try:
        proc = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{relpath}"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def main() -> None:
    inv_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/survey/inventory.json"
    findings_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/survey/findings"
    ref = (sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else "") or "HEAD"

    root = find_repo_root()
    inv_path = root / inv_rel
    if not inv_path.is_file():
        emit("skip", report=f"no inventory at {inv_rel} — nothing was surveyed")
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
        units = data.get("units")
        assert isinstance(units, list)
    except (json.JSONDecodeError, ValueError, AssertionError):
        emit("no", [f"inventory at {inv_rel} is not parseable JSON with a `units` list"],
             report="inventory unreadable")

    errors: list[str] = []
    counts = {"assessed": 0, "clean": 0, "blocked": 0, "pending": 0}
    current_ids: set[str] = set()
    current_paths: list[str] = []

    for u in units:
        if not isinstance(u, dict) or not str(u.get("id") or ""):
            errors.append(f"  - [malformed-unit] inventory entry {u!r} has no id")
            continue
        unit_id = str(u["id"])
        current_ids.add(unit_id)
        current_paths.append(str(u.get("path") or unit_id))
        status = u.get("status")
        if status not in UNIT_STATUSES:
            errors.append(f"  - [bad-status] '{unit_id}' has status '{status}'")
            continue
        counts[status] += 1
        if status == "pending":
            errors.append(f"  - [pending] '{unit_id}' has not been assessed — the loop must "
                          f"re-enter (this gate never waves a pending unit through)")
            continue

        record_path = root / findings_rel / f"{record_slug(unit_id)}.md"
        if not record_path.is_file():
            errors.append(f"  - [missing-record] '{unit_id}' is '{status}' but has no finding "
                          f"record at {findings_rel}/{record_slug(unit_id)}.md")
            continue
        try:
            record = load_record(record_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"  - [invalid-record] '{unit_id}': {exc}")
            continue
        struct = record_errors(record, unit_id)
        if struct:
            errors.append(f"  - [invalid-record] '{unit_id}': " + "; ".join(struct))
            continue
        if record.get("status") != status:
            errors.append(f"  - [status-mismatch] '{unit_id}' is '{status}' in the inventory "
                          f"but '{record.get('status')}' in its record — one claim, two files, "
                          f"they must agree")
            continue
        if status == "blocked" and record.get("disposition") != "accepted":
            gaps = "; ".join(str(g) for g in (record.get("openGaps") or []))[:300]
            errors.append(f"  - [blocked] '{unit_id}' is an OPEN gap ({gaps}) — fix the "
                          f"precondition and set the unit's inventory status back to 'pending', "
                          f"or record `disposition: accepted` (with the reason) in its record")

    # ── Reconcile-style shrinkage vs the committed baseline ────────────────────────────
    base_text = git_show(root, ref, inv_rel)
    if base_text is not None:
        try:
            base_units = json.loads(base_text).get("units") or []
        except (json.JSONDecodeError, ValueError):
            base_units = []
        for bu in base_units:
            if not isinstance(bu, dict):
                continue
            bid = str(bu.get("id") or "")
            if not bid or bid in current_ids:
                continue
            bpath = str(bu.get("path") or bid)
            if any(p.startswith(bpath + "/") for p in current_paths):
                continue  # split lineage — the parent was replaced by its children
            errors.append(f"  - [dropped-unit] '{bid}' was in the committed inventory ({ref}) "
                          f"but is gone now with no split lineage and no record — a frozen-list "
                          f"drop is a regression; restore it or split it properly")

    total = len(current_ids)
    report = (f"survey coverage: {total} unit(s) — {counts['assessed']} assessed, "
              f"{counts['clean']} clean, {counts['blocked']} blocked, "
              f"{counts['pending']} pending; {len(errors)} problem(s)")
    if errors:
        emit("no", ["the survey's coverage claim does not hold yet:", *errors], report)
    emit("yes", report=report)


if __name__ == "__main__":
    main()
