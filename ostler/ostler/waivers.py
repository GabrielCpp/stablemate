"""`ostler doctor` waivers — an accepted-defect register that downgrades, never hides.

A doctor waiver records a deliberate, reviewed decision that a *real* error-level finding will be
tolerated for now — typically a defect whose only true fix is a code change the current run cannot
make (two controls that genuinely co-render with the same accessible name; an operable control the
source leaves unnamed). Unlike `exclusive-with:` — which asserts a collision does not happen — a
waiver asserts it *does* happen and is knowingly accepted. So the finding is not dropped: `doctor`
downgrades it from `error` to `warn`, keeps it in the report with the reason and the backlog id that
tracks its real fix, and only stops it from *gating* (the exit code and the okf-builder checkpoint
count `error` findings, never `warn`). The waiver is committed, diffable and reason-carrying — the
same design as coverage waivers (`coverage.load_waivers`) — so the judgement survives instead of
being re-litigated every round, and un-waiving is a one-line diff.

Store: ``docs/doctor-waivers.json`` at the graph root, next to ``docs/backlog.md``. Shape::

    {"waivers": [
      {"code": "ambiguous-locator",
       "ref":  "docs/features/web/gui/components/navbar-items.md#screen/save",
       "reason": "two Save controls co-render; needs distinct aria-labels in source",
       "backlog": "fix-ambiguous-locator-navbar-items-save"}
    ]}

A missing file means nothing is waived (not an error).
"""
from __future__ import annotations

import json
from pathlib import Path

from ostler.coverage import normalize_ref
from ostler.model import Graph

WAIVERS_FILE = "doctor-waivers.json"


def _path(graph: Graph) -> Path:
    return graph.root / "docs" / WAIVERS_FILE


def load(graph: Graph) -> dict[tuple[str, str], dict[str, str]]:
    """Waivers keyed by ``(code, normalized ref)`` → the entry (``reason``, ``backlog``).

    A missing or unreadable file yields ``{}`` — the fail-safe is "nothing waived", so a corrupt
    register can never silence a real error, only fail to silence an accepted one.
    """
    file = _path(graph)
    if not file.exists():
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = data.get("waivers", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        return {}
    out: dict[tuple[str, str], dict[str, str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code", "")).strip()
        ref = normalize_ref(str(entry.get("ref", "")))
        if not code or not ref:
            continue
        out[(code, ref)] = {
            "reason": str(entry.get("reason", "")),
            "backlog": str(entry.get("backlog", "")),
        }
    return out


def add(graph: Graph, code: str, ref: str, reason: str, backlog: str = "") -> bool:
    """Record (or update) a waiver for ``(code, ref)``. Returns True if the store changed.

    Idempotent on ``(code, normalized ref)``: re-waiving the same finding updates its reason/backlog
    rather than appending a duplicate, so an auto-waive step that re-runs never piles up entries.
    """
    code = str(code).strip()
    nref = normalize_ref(str(ref))
    if not code or not nref:
        return False
    file = _path(graph)
    entries: list[dict[str, str]] = []
    if file.exists():
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            raw = data.get("waivers", data) if isinstance(data, dict) else data
            if isinstance(raw, list):
                entries = [e for e in raw if isinstance(e, dict)]
        except (OSError, json.JSONDecodeError):
            entries = []
    updated = {"code": code, "ref": ref.strip(), "reason": str(reason), "backlog": str(backlog)}
    for i, e in enumerate(entries):
        if str(e.get("code", "")).strip() == code and normalize_ref(str(e.get("ref", ""))) == nref:
            entries[i] = updated
            break
    else:
        entries.append(updated)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps({"waivers": entries}, indent=2) + "\n", encoding="utf-8")
    return True
