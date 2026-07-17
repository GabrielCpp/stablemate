#!/usr/bin/env python3
"""Drain the dream flow's proposals into a durable, deduplicated cross-run ledger.

This is what makes reflection REAL instead of a per-run dead doc. The dream agent writes
its structured proposals to an inbox (`docs/.dream-improvements.inbox.json`); this script
merges them into a persistent ledger (`docs/workflow-improvements.json` + a rendered
`docs/workflow-improvements.md`), deduping by (layer, title) and bumping an `observed`
count + appending the run id so RECURRING friction accumulates evidence and rises in
priority. A human reviews that one ledger and applies (or rejects) the changes —
autonomously self-applying workflow/prompt edits would be unsafe, so the loop closes at
human review, not auto-mutation.

Args:
    argv[1]  docs_path   repo root (empty → CWD).
    argv[2]  run_dir     the reflected run's dir (its basename is used as the run id
                         for provenance in the ledger).

Stdlib-only. Emits: {"improvements_recorded": {"added": N, "bumped": M, "ledger": "<path>"}}.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root

INBOX = "docs/.dream-improvements.inbox.json"
LEDGER_JSON = "docs/workflow-improvements.json"
LEDGER_MD = "docs/workflow-improvements.md"
VALID_LAYERS = {"base-prompt", "repo-flavor", "workflow-dag", "ostler", "infra"}


def _key(layer: str, title: str) -> str:
    return (layer.strip().lower() + "|" + " ".join(title.strip().lower().split()))


def _render_md(ledger: list[dict]) -> str:
    # Open items first, then by evidence (observed count) — recurring friction on top.
    rows = sorted(ledger, key=lambda r: (r.get("status") == "done", -int(r.get("observed", 1))))
    out = ["# Workflow self-improvement ledger",
           "",
           "Proposals from the `dream` flow (offline reflection over run transcripts).",
           "Deduped across runs; `observed` counts how many runs surfaced the same friction.",
           "A human reviews and applies — the dream flow never self-mutates the workflow.",
           ""]
    for r in rows:
        box = "x" if r.get("status") == "done" else " "
        out.append(f"- [{box}] **[{r.get('layer','?')}]** {r.get('title','').strip()} "
                   f"(observed ×{r.get('observed',1)})")
        if r.get("detail"):
            out.append(f"  - {r['detail'].strip()}")
        if r.get("where"):
            out.append(f"  - Where: `{r['where'].strip()}`")
        if r.get("runs"):
            out.append(f"  - Runs: {', '.join(r['runs'][-5:])}")
    out.append("")
    return "\n".join(out)


def main(logger: logging.Logger) -> None:
    docs_path = sys.argv[1] if len(sys.argv) > 1 else ""
    run_dir_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    run_id = Path(run_dir_arg).name if run_dir_arg else "unknown-run"
    root = find_docs_root(docs_path)

    inbox_path = root / INBOX
    if not inbox_path.is_file():
        logger.info("no inbox at %s — nothing to record", inbox_path)
        print(json.dumps({"improvements_recorded": {"added": 0, "bumped": 0, "ledger": LEDGER_MD,
                                                     "note": "no inbox — nothing to record"}}))
        return
    try:
        proposals = json.loads(inbox_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("unreadable inbox %s: %s", inbox_path, exc)
        print(json.dumps({"improvements_recorded": {"added": 0, "bumped": 0, "ledger": LEDGER_MD,
                                                     "error": f"unreadable inbox ({exc})"}}))
        return
    if isinstance(proposals, dict):
        proposals = proposals.get("proposals", [])
    if not isinstance(proposals, list):
        proposals = []

    ledger_path = root / LEDGER_JSON
    ledger: list[dict] = []
    if ledger_path.is_file():
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8")) or []
        except (ValueError, OSError):
            ledger = []
    index = {_key(r.get("layer", ""), r.get("title", "")): r for r in ledger}

    added = bumped = 0
    for p in proposals:
        if not isinstance(p, dict):
            continue
        layer = str(p.get("layer", "")).strip().lower()
        title = str(p.get("title", "")).strip()
        if not title:
            continue
        if layer not in VALID_LAYERS:
            layer = "infra"  # keep it in the ledger under a safe default rather than drop
        k = _key(layer, title)
        existing = index.get(k)
        if existing:
            existing["observed"] = int(existing.get("observed", 1)) + 1
            runs = existing.setdefault("runs", [])
            if run_id not in runs:
                runs.append(run_id)
            # Keep the freshest detail/where if the new one is non-empty.
            if p.get("detail"):
                existing["detail"] = str(p["detail"]).strip()
            if p.get("where"):
                existing["where"] = str(p["where"]).strip()
            bumped += 1
        else:
            rec = {
                "layer": layer,
                "title": title,
                "detail": str(p.get("detail", "")).strip(),
                "where": str(p.get("where", "")).strip(),
                "impact": str(p.get("impact", "")).strip(),
                "observed": 1,
                "runs": [run_id],
                "status": "open",
            }
            ledger.append(rec)
            index[k] = rec
            added += 1

    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    (root / LEDGER_MD).write_text(_render_md(ledger), encoding="utf-8")
    # Clear the inbox so the next dream run starts clean.
    try:
        inbox_path.unlink()
    except OSError:
        pass

    logger.info("recorded %d added, %d bumped (ledger total %d)", added, bumped, len(ledger))
    print(json.dumps({"improvements_recorded": {"added": added, "bumped": bumped,
                                                "ledger": LEDGER_MD, "total": len(ledger)}}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("record-improvements"))
