"""The drain's two primitives: take an item, and write back what came of it.

Ported from `base-library/workflows/okf-builder/scripts/{select-item,record}.py`. Both
are used by the main graph and by the walk sub-flow against their own worklists, which is
why they take the path as a parameter rather than reading it off a context.

The one behavioral divergence is in `record`: its `current` and `discovered` arguments
were JSON **strings**, because a YAML template argument is text. The YAML rendered them
three different ways — `| tojson`, a bare `{{ }}` (`seed_fixup`, which passed a list that
had already been serialized once), and `""` for "nothing to close" — and `record.py`
carried an `ast.literal_eval` fallback for the spelling that came back as a Python repr.
Here they are a `dict` and a `list[dict]` bound by `inspect.signature` at the callsite, so
the round trip is gone and the fallback along with it — as are the two `logger.warning`s
that reported a mangled one. Nothing is narrowed by choice: those arms handled a *rendered
string*, and no caller in this shape can produce one. What they protected against is now
a `TypeError` at the transition instead of a silently-dropped discovery list.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from workhorse import worklist as wl
from workhorse_workflows.okf_builder.nodes._blueprint import blueprint
from workhorse_workflows.okf_builder.schemas import Pick, Recorded


def _norm(s: object) -> str:
    return " ".join(str(s or "").split()).strip().lower()


@blueprint.node
def select_item(
    logger: logging.Logger,
    worklist_path: str,
    max_items: int = 0,
    done_baseline: int = 0,
) -> Pick:
    """Pop the next pending item and mark it active.

    Prefers an already-`active` item (a crash mid-investigation is re-picked, not
    skipped), else the first `pending`. Empty → the drain is dry and the caller converges.

    `max_items` caps investigations completed by THIS run, measured against
    `done_baseline`. Counting `done` over the whole file would make it a *lifetime* cap:
    a resumed worklist already at the ceiling is instantly over budget, hands out zero
    items, and the run reports success having done nothing.
    """
    path = Path(worklist_path)
    data = json.loads(path.read_text())
    # One worklist snapshot drives both the budget math (counts.done for the per-run cap)
    # and the dashboard (progress "3/12" + the kinds line "5 surface · 3 layer" — okf's
    # items are multi-kind, so that composition is the natural activity subtitle). The
    # rows already carry `kind`/`status`, so they parse straight into the primitive's
    # `WorkItem` (no Backend; this node owns the JSON read/write and the budget cap the
    # primitive knows nothing about). okf's own fields — `target`, `context` — ride
    # top-level and survive the round trip untouched. See workhorse.worklist.
    items = [wl.WorkItem.model_validate(row) for row in data.get("items", [])]
    snap = wl.snapshot(items)
    done = snap.counts.done
    # Clamp: a baseline above the count means the worklist shrank under the run (a reset
    # mid-flight). Trusting it would make `done_this_run` negative and the cap unreachable.
    this_run = max(0, done - min(done_baseline, done))
    logger.info(
        "worklist %s: %d items, %d done (%d this run, baseline %d), cap %s",
        path, len(items), done, this_run, done_baseline, max_items or "none",
    )

    if max_items and this_run >= max_items:
        # Over budget: stop handing out work so the run converges the partial book
        # rather than burning quota all night. Pending items remain for a later resume.
        logger.warning(
            "over budget — %d done this run reaches the cap of %d; handing out no more "
            "work with %d still pending (resume to continue)",
            this_run, max_items, snap.counts.pending,
        )
        return Pick(
            over_budget=True,
            pending_count=snap.counts.pending,
            done_count=done,
            done_this_run=this_run,
            progress=snap.progress,
            kinds=snap.kinds,
        )

    pick = wl.select_next(items)  # active-first crash-safe re-pick, then first pending
    if pick is None:
        logger.info("drain is dry — no active or pending items; handing off to checkpoint")
        return Pick(
            done_count=done,
            done_this_run=this_run,
            progress=snap.progress,
            kinds=snap.kinds,
        )

    resumed = pick.status == "active"
    pick.status = "active"
    # `exclude_unset` so writing the file back adds no key okf never wrote — the worklist
    # is the workflow's document, and this node only flips one status in it.
    data["items"] = [it.model_dump(exclude_unset=True) for it in items]
    path.write_text(json.dumps(data, indent=2))
    pend = wl.counts(items).pending  # one fewer after the flip
    target = str(getattr(pick, "target", "") or "")
    logger.info(
        "picked %s item '%s' (%s), %d still pending",
        "resumed active" if resumed else "next pending",
        target or "?", pick.kind or "?", pend,
    )
    return Pick(
        has_item=True,
        current_item=pick.model_dump(exclude_unset=True),
        item_kind=pick.kind,
        item_target=target,
        item_context=str(getattr(pick, "context", "") or ""),
        pending_count=pend,
        done_count=done,
        done_this_run=this_run,
        progress=snap.progress,
        kinds=snap.kinds,
    )


@blueprint.node
def record(
    logger: logging.Logger,
    worklist_path: str,
    current: dict[str, Any] | None = None,
    discovered: list[dict[str, Any]] | None = None,
) -> Recorded:
    """Mark the current item done and merge newly-discovered items.

    The universal worklist mutator — used after enumerate (seed surfaces), investigate
    (seed an item's spawned children), checkpoint (seed fixups), and recheck (seed
    coverage/journey items). Dedupes by `(kind, target)` against ALL items, normalized.
    A coverage recheck may set `requeue: true` to reopen an already-done below-bar item.
    """
    path = Path(worklist_path)
    data = json.loads(path.read_text())
    items = data.get("items", [])
    by_key = {(_norm(i.get("kind")), _norm(i.get("target"))): i for i in items}

    if current:
        ck = (_norm(current.get("kind")), _norm(current.get("target")))
        logger.info(
            "marking item '%s' (%s) done", current.get("target", "?"), current.get("kind", "?")
        )
        for i in items:
            if (_norm(i.get("kind")), _norm(i.get("target"))) == ck:
                i["status"] = "done"

    added = 0
    for d in discovered or []:
        if not isinstance(d, dict):
            continue
        k = (_norm(d.get("kind")), _norm(d.get("target")))
        if not d.get("kind") or not d.get("target"):
            continue
        existing = by_key.get(k)
        if existing:
            if d.get("requeue") is True and existing.get("status") == "done":
                existing["status"] = "pending"
                existing["context"] = d.get("context", existing.get("context", ""))
                added += 1
            continue
        items.append({
            "kind": d["kind"], "target": d["target"],
            "context": d.get("context", ""), "status": "pending",
        })
        by_key[k] = items[-1]
        added += 1

    data["items"] = items
    path.write_text(json.dumps(data, indent=2))
    done = sum(1 for i in items if i.get("status") == "done")
    pend = sum(1 for i in items if i.get("status") == "pending")
    logger.info(
        "worklist %s: added %d new item(s), now %d done / %d pending", path, added, done, pend
    )
    return Recorded(done_count=done, pending_count=pend, added=added)


__all__ = ["record", "select_item"]
