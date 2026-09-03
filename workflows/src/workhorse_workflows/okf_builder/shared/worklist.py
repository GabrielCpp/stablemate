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
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Pick, Recorded


#: How many times one target may be re-queued before the row stops reopening and blocks.
#: A repair that has not landed in three turns against the same finding is a repair the
#: agent cannot make from the book, and a fourth turn spends a turn to learn that again.
#:
#: It lives here rather than beside `MAX_STALL_ROUNDS` in `main/flow.py` because `record`
#: is what counts, and `shared/` must not import `main/`. `flow.py` imports it back for the
#: gate's wording, so the number an operator reads is the number that blocked the row.
MAX_TARGET_ATTEMPTS = 3


def _norm(s: object) -> str:
    return " ".join(str(s or "").split()).strip().lower()


def book_has_docs(features: Path) -> bool:
    """Whether this book has ever been written — one markdown file anywhere under it.

    Public because two callers ask it and the answer has to be the same one: this module
    decides whether a worklist claiming completed work can be believed, and `prepare`
    decides whether the run reconciles an existing book or fills an empty one top-down.
    """
    return features.is_dir() and any(features.rglob("*.md"))


def load_worklist(
    path: Path,
    service: str,
    features: Path,
    *,
    scope_id: str = "bulk",
    mode: str = "bulk",
) -> tuple[dict[str, Any], bool]:
    """Load compatible drain memory, or return a freshly stamped worklist."""
    fresh: dict[str, Any] = {
        "service": service,
        "book": str(features),
        "scope_id": scope_id,
        "mode": mode,
        "items": [],
    }
    if not path.exists():
        return fresh, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fresh, True
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return fresh, True
    if data.get("service", service) != service:
        return fresh, True
    if data.get("scope_id", "bulk") != scope_id or data.get("mode", "bulk") != mode:
        return fresh, True
    done = sum(1 for item in data["items"] if item.get("status") == "done")
    if done and not book_has_docs(features):
        return fresh, True
    data.setdefault("service", service)
    data["scope_id"] = scope_id
    data["mode"] = mode
    data["book"] = str(features)
    return data, False


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

    pick = wl.select_next(items)  # active-first crash-safe re-pick, then first pending
    if pick is None:
        logger.info("drain is dry — no active or pending items; handing off to checkpoint")
        return Pick(
            done_count=done,
            done_this_run=this_run,
            progress=snap.progress,
            kinds=snap.kinds,
        )

    if max_items and this_run >= max_items:
        # Over budget: stop handing out work so the run converges the partial book
        # rather than burning quota all night. Pending items remain for a later resume.
        # Checked only when there IS a next item: a drain that finished its last item
        # exactly at the cap is dry, not over budget, and blocking it would ask the
        # operator for an allowance nothing is waiting to spend.
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
        # `fix:<code>` is the checkpoint's spelling for a repair item; splitting the code out
        # here keeps the template's `{% include %}` from having to parse the kind.
        item_code=pick.kind.removeprefix("fix:") if pick.kind.startswith("fix:") else "",
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
    doc_status: str = "",
    note: str = "",
    max_attempts: int = MAX_TARGET_ATTEMPTS,
    unblock: bool = False,
    only: tuple[str, ...] = (),
) -> Recorded:
    """Mark the current item done, merge newly-discovered items, and count the re-tries.

    The universal worklist mutator — used after enumerate (seed surfaces), investigate
    (seed an item's spawned children), checkpoint (seed fixups), and recheck (seed
    coverage/journey items). Dedupes by `(kind, target)` against ALL items, normalized.
    A coverage recheck — and every repair item the checkpoint queues — may set
    `requeue: true` to reopen an already-done row.

    **A reopen is a re-try, and a re-try is counted.** `record` is both the only place a
    row is closed and the only place one is reopened, so the per-target `attempts` counter
    belongs here and nowhere else. A row that reaches `max_attempts` is not reopened again:
    it goes `blocked`, carrying whatever the last turn said about why it could not finish.
    `blocked` is `workhorse.worklist.Scheme`'s own third status — `select_next` already
    passes over it and `WorkCounts` already buckets it — so nothing downstream learns a new
    word, and the row stops being handed out instead of being silently marked done.

    Without this, a finding doctor keeps re-raising is re-queued forever: the turn that
    could not fix it closes it `done`, the checkpoint re-queues it, and nothing anywhere
    counts. That is the loop that ran nineteen rounds on sixteen findings.

    `doc_status`/`note` are the *closing* turn's own verdict on `current`. They are
    recorded on the row for every kind of item, not just `change`: a repair turn reporting
    `partial` or `skipped` is stating that this target is unrepairable from the book, and
    that sentence is exactly what the operator gate needs to print.

    `unblock` is the answer to that gate: it returns every blocked row to the drain with a
    fresh attempt allowance, the same shape the coverage gate uses when an operator grants
    another `MAX_RESCAN_ROUNDS`. Without it the gate would be a dead end — a human who
    repaired the book by hand could not tell the run to try again. `only` narrows it to
    the targets named; the operator's answer reaches every blocked row, and it also drops
    the verdict an adjudication wrote, because the answer is a statement that something
    changed and the next block is judged afresh.
    """
    path = Path(worklist_path)
    data = json.loads(path.read_text())
    items = data.get("items", [])
    by_key = {(_norm(i.get("kind")), _norm(i.get("target"))): i for i in items}

    if unblock:
        for i in items:
            if i.get("status") != "blocked":
                continue
            if only and str(i.get("target", "")) not in only:
                continue
            logger.info("operator granted a fresh allowance for '%s'", i.get("target"))
            i["status"] = "pending"
            i["attempts"] = 0
            for key in ("blocked_reason", "verdict", "chain"):
                i.pop(key, None)

    if current:
        ck = (_norm(current.get("kind")), _norm(current.get("target")))
        logger.info(
            "marking item '%s' (%s) done%s",
            current.get("target", "?"), current.get("kind", "?"),
            f" ({doc_status})" if doc_status else "",
        )
        for i in items:
            if (_norm(i.get("kind")), _norm(i.get("target"))) == ck:
                i["status"] = "done"
                if doc_status:
                    i["doc_status"] = doc_status
                if note:
                    i["note"] = note

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
                attempts = int(existing.get("attempts", 0) or 0) + 1
                existing["attempts"] = attempts
                if attempts >= max_attempts:
                    last = str(existing.get("doc_status", ""))
                    reason = str(existing.get("note", "")) or (
                        f"the last turn reported `{last}` and the finding still stands"
                        if last
                        else "the turn gave no reason"
                    )
                    existing["status"] = "blocked"
                    existing["blocked_reason"] = reason
                    logger.warning(
                        "'%s' (%s) survived %d repair attempts — blocking it rather than "
                        "re-queueing: %s",
                        existing.get("target"), existing.get("kind"), attempts, reason,
                    )
                    continue
                existing["status"] = "pending"
                existing["context"] = d.get("context", existing.get("context", ""))
                added += 1
            continue
        items.append({
            "kind": d["kind"], "target": d["target"],
            "context": d.get("context", ""), "status": "pending",
            # Written explicitly, never left to a model default: `select_item` writes the
            # file back with `exclude_unset=True`, so a field no row ever carried is
            # dropped on the next pick and the count restarts at zero every round.
            "attempts": 0,
        })
        by_key[k] = items[-1]
        added += 1

    data["items"] = items
    path.write_text(json.dumps(data, indent=2))
    done = sum(1 for i in items if i.get("status") == "done")
    pend = sum(1 for i in items if i.get("status") == "pending")
    # The *standing* blocked set, not only what this write blocked: the gate reports what
    # is still stuck, and a resumed run that blocks nothing new must not hand the operator
    # a shorter list than the round that first blocked them.
    blocked = [
        {
            "kind": str(i.get("kind", "")),
            "target": str(i.get("target", "")),
            "attempts": int(i.get("attempts", 0) or 0),
            "reason": str(i.get("blocked_reason", "")),
            "verdict": str(i.get("verdict", "")),
            "chain": str(i.get("chain", "")),
            "seed": str(i.get("seed", "")),
        }
        for i in items
        if i.get("status") == "blocked"
    ]
    logger.info(
        "worklist %s: added %d new item(s), now %d done / %d pending / %d blocked",
        path, added, done, pend, len(blocked),
    )
    return Recorded(
        done_count=done,
        pending_count=pend,
        added=added,
        blocked=blocked,
        blocked_count=len(blocked),
    )


__all__ = ["MAX_TARGET_ATTEMPTS", "book_has_docs", "load_worklist", "record", "select_item"]
