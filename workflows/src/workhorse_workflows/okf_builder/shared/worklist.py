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

import hashlib
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any

from ostler import markdown
from ostler.model import document_anchors
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


#: How many findings one repair turn may carry across the rows it batches. The same bound
#: as one checkpoint item (`checkpoint.MAX_FINDINGS_PER_ITEM`): past it a large turn invites
#: a shallow pass over its tail, whether the tail is one row or several.
MAX_BATCH_FINDINGS = 25


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


def repair_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """The `(kind, target)` identity of each row, normalized the way `record` dedupes."""
    return {(_norm(r.get("kind")), _norm(r.get("target"))) for r in rows if isinstance(r, dict)}


def doctor_row(row: dict[str, Any]) -> bool:
    """Whether a worklist row is a doctor finding's repair — the only rows doctor may settle.

    The `fix:` prefix is not the test: the coverage join queues `fix:stale-citation` rows
    too, and doctor never reports those, so reading the prefix alone closes a regrounding
    row as "stale" the moment any doctor pass runs. The checkpoint writes the findings that
    back a row into its context (`_repair_items`), so a row carrying them is one whose
    standing a doctor read can answer.
    """
    if not str(row.get("kind", "")).startswith("fix:"):
        return False
    raw = row.get("context", "")
    try:
        context = raw if isinstance(raw, dict) else json.loads(str(raw or "{}"))
    except ValueError:
        return False
    return isinstance(context, dict) and "findings" in context


def settle_stale_rows(
    items: list[dict[str, Any]], standing: list[dict[str, Any]], *, where: str
) -> int:
    """Close every open doctor repair row doctor no longer reports. Returns how many.

    `standing` is the repair items a fresh doctor pass would queue — the rows a finding
    still backs. An open repair outside that set is a turn that would be spent finding
    nothing to do: a rule retired under the run, a finding an earlier repair of the same
    node already cleared, an autofix that moved.

    **Blocked rows too.** `blocked` records that a finding survived its attempts *as of the
    doctor read that blocked it*; the gate that prints it asserts the finding still stands.
    The book is a working tree other writers share, so that claim is only as old as its
    observation — a row left out of the settle kept a run parked for hours on a gate whose
    findings someone else had already cleared. What the operator reads has to be what
    doctor reports now, so a blocked row is settled by the same rule as a pending one.
    Only doctor's rows (`doctor_row`); a discovery item or a coverage row is not doctor's
    to settle.

    Shared by `record`'s checkpoint write and `checkpoint.settle_stale`, which does the
    same thing mid-drain and before a blocked gate; `where` is the closing note's word for
    which one it was.
    """
    keys = repair_keys(standing)
    settled = 0
    for i in items:
        if i.get("status") not in ("pending", "blocked") or not doctor_row(i):
            continue
        if (_norm(i.get("kind")), _norm(i.get("target"))) in keys:
            continue
        i["status"] = "done"
        i["doc_status"] = "stale"
        i["note"] = f"doctor no longer reports this finding; closed {where}"
        settled += 1
    return settled


def reopen_row(
    logger: logging.Logger,
    existing: dict[str, Any],
    standing: dict[str, Any],
    repo_root: str,
    max_attempts: int = MAX_TARGET_ATTEMPTS,
) -> bool:
    """Reopen a `done` row whose finding still stands; True when it went back to `pending`.

    The one requeue rule, shared by `record` (the checkpoint's write) and
    `checkpoint.settle_stale` (the same doctor read, mid-drain) — see `record` for why an
    attempt is counted only against the node the turn left. A row that has spent
    `max_attempts` goes `blocked` instead, and False is returned.
    """
    # A `stale` close was the settle's, not a repair turn's: no turn tried the
    # finding, so reopening it spends no attempt, and the settle's note must not
    # survive to be quoted as the reason a standing finding could not be fixed.
    # A blocked row settled `stale` keeps its `blocked_reason`, which is the
    # last real turn's account, and re-blocks on it.
    prior = ""
    sealed = str(existing.pop("closed_digest", "") or "")
    moved = bool(sealed and repo_root) and sealed != repair_scope_digest(
        repo_root, str(existing.get("context", "")))
    if existing.get("doc_status") == "stale":
        existing.pop("doc_status", None)
        existing.pop("note", None)
        prior = str(existing.get("blocked_reason", ""))
        attempts = int(existing.get("attempts", 0) or 0)
    elif moved:
        logger.info(
            "'%s' (%s) still stands, but its node changed since the turn closed "
            "it — reopening without counting an attempt",
            existing.get("target"), existing.get("kind"),
        )
        existing.pop("doc_status", None)
        existing.pop("note", None)
        attempts = int(existing.get("attempts", 0) or 0)
    else:
        attempts = int(existing.get("attempts", 0) or 0) + 1
    existing["attempts"] = attempts
    if attempts >= max_attempts:
        last = str(existing.get("doc_status", ""))
        reason = str(existing.get("note", "")) or prior or (
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
        return False
    existing["status"] = "pending"
    existing["context"] = standing.get("context", existing.get("context", ""))
    return True


def _repair_scope(row: dict[str, Any]) -> tuple[str, list[dict[str, Any]]] | None:
    """The one book file a repair row is about, and its findings — or None if it has none.

    A row joins a batch only when its scope is one file: a group finding (`related`) spans
    several, and a `fix:stale-citation` row moves its own watermark when it closes
    (`advance_watermark` reads one row's context), so both stay turns of their own.
    """
    kind = str(row.get("kind", ""))
    if not kind.startswith("fix:") or kind == "fix:stale-citation":
        return None
    try:
        ctx = json.loads(str(row.get("context", "") or ""))
    except json.JSONDecodeError:
        return None
    if not isinstance(ctx, dict) or ctx.get("related") or not ctx.get("path"):
        return None
    findings = ctx.get("findings")
    return str(ctx["path"]), findings if isinstance(findings, list) else []


def _batch(rows: list[dict[str, Any]], first: int) -> list[int]:
    """The rows one repair turn takes: `first`, plus the open repair rows on its file.

    **The row is the unit of tracking; the file is the unit of work.** A checkpoint row is
    one `(file, node, code)`, so a finding keeps one identity and one `attempts` count
    across rounds, and its prompt fragment is known before the turn starts. But the cost of
    a turn is orientation — loading the method, reading the document and the source it
    cites — and that is paid per file, not per code. Handing a document's rows out one turn
    each paid it once per row: on a backfilled book the median document carried 10–21
    rows. Instructions compose where orientation does not, so the turn takes every open
    row on the file and the prompt includes one fragment per distinct code.

    Rows are taken in worklist order, which is the checkpoint's drain order, while their
    findings total at most `MAX_BATCH_FINDINGS`. `first` is always taken, whatever its size.
    An `active` row is one a crashed turn already held, so the same batch re-forms on the
    re-pick.
    """
    scope = _repair_scope(rows[first])
    if scope is None:
        return [first]
    path, findings = scope
    taken, total = [first], len(findings)
    for n, row in enumerate(rows):
        if n == first or row.get("status") not in ("active", "pending"):
            continue
        other = _repair_scope(row)
        if other is None or other[0] != path:
            continue
        if total + len(other[1]) > MAX_BATCH_FINDINGS:
            continue
        taken.append(n)
        total += len(other[1])
    return taken


def _batch_context(rows: list[dict[str, Any]]) -> str:
    """One repair context over several rows on one file: every node, code and finding.

    The keys a single row's context carries keep their meaning — `path`, `grounded`,
    `findings` — so the prompt and `repair_power` read a batch the way they read one row;
    `node`/`code` become the lists `nodes`/`codes`.
    """
    contexts = [json.loads(str(r.get("context", ""))) for r in rows]
    findings = [f for c in contexts for f in (c.get("findings") or [])]
    return json.dumps({
        "path": contexts[0]["path"],
        "nodes": list(dict.fromkeys(str(c.get("node", "")) for c in contexts)),
        "codes": list(dict.fromkeys(str(r.get("kind", "")).removeprefix("fix:") for r in rows)),
        "grounded": any(c.get("grounded") is True for c in contexts),
        "findings": sorted(findings, key=lambda f: int(f.get("line", 0) or 0)),
    }, indent=2)


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
    rows = [it.model_dump(exclude_unset=True) for it in items]
    taken = _batch(rows, next(n for n, it in enumerate(items) if it is pick))
    for n in taken:
        items[n].status = "active"
        rows[n]["status"] = "active"
    # `exclude_unset` so writing the file back adds no key okf never wrote — the worklist
    # is the workflow's document, and this node only flips statuses in it.
    data["items"] = rows
    path.write_text(json.dumps(data, indent=2))
    pend = wl.counts(items).pending  # fewer after the flip
    target = str(getattr(pick, "target", "") or "")
    batch = [rows[n] for n in taken]
    kinds = [str(r.get("kind", "")) for r in batch]
    codes = list(dict.fromkeys(k.removeprefix("fix:") for k in kinds if k.startswith("fix:")))
    logger.info(
        "picked %s item '%s' (%s)%s, %d still pending",
        "resumed active" if resumed else "next pending",
        target or "?", pick.kind or "?",
        f" with {len(batch) - 1} more row(s) on its file" if len(batch) > 1 else "",
        pend,
    )
    return Pick(
        has_item=True,
        current_item=batch[0],
        batch=batch[1:],
        item_kind=pick.kind,
        # `fix:<code>` is the checkpoint's spelling for a repair item; splitting the code out
        # here keeps the template's `{% include %}` from having to parse the kind.
        item_code=codes[0] if codes else "",
        item_codes=codes,
        item_target=target,
        item_context=(
            _batch_context(batch) if len(batch) > 1 else str(getattr(pick, "context", "") or "")
        ),
        pending_count=pend,
        done_count=done,
        done_this_run=this_run,
        progress=snap.progress,
        kinds=snap.kinds,
    )


def _node_region(text: str, node: str, path: str) -> str | None:
    """The lines a node owns in one document, or None when the document has no such node.

    A file node — its id is the bare path — owns the whole document. A section node owns its
    heading through its first child heading: a `#### field:` under a record is its own node,
    and a repair on it is not a change to the record.
    """
    if node == path:
        return text
    anchor = node.removeprefix(path + "#")
    doc = markdown.split(text)
    anchors = document_anchors(doc)
    for section in doc.walk_sections():
        if anchors.get(section.line_start) == anchor:
            end = section.children[0].line_start if section.children else section.line_end
            return "\n".join(section.body_lines[section.line_start:end])
    return None


def repair_scope_digest(repo_root: str, context: str) -> str:
    """A fingerprint of the book text a repair item is about, as it stands on disk now.

    The scope is what the item's own context names: its `node` in `path`, or every member
    of `related` for a group finding. Two reads are equal exactly when nothing in that scope
    changed between them — which is the observation `record` needs to tell "the turn's
    repair did not hold" from "the node is no longer what the turn left".

    Empty when the context names no scope (not a repair item); a missing file or node is
    part of the fingerprint, so a node that vanished and stayed vanished still compares
    equal to itself.
    """
    try:
        ctx = json.loads(context) if context else {}
    except json.JSONDecodeError:
        return ""
    if not isinstance(ctx, dict):
        return ""
    if ctx.get("node") and ctx.get("path"):
        members = [str(ctx["node"])]
    else:
        members = [str(m) for m in ctx.get("related") or []]
    if not members:
        return ""
    root = Path(repo_root)
    digest = hashlib.sha256()
    for member in sorted(members):
        path = member.split("#", 1)[0]
        try:
            region = _node_region((root / path).read_text(encoding="utf-8"), member, path)
        except OSError:
            region = None
        digest.update(member.encode())
        digest.update(b"\0")
        digest.update(b"\1absent" if region is None else region.encode())
        digest.update(b"\0")
    return digest.hexdigest()


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
    settle_fix_items: bool = False,
    repo_root: str = "",
    batch: list[dict[str, Any]] | None = None,
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

    `settle_fix_items` says `discovered` is the *whole* standing doctor report — the
    checkpoint's call, and only that call. An open doctor row the report no longer names
    is a finding that stopped firing: repaired by a neighbouring turn, or retired by a
    doctor rule that changed under the run. It is closed as `stale` here rather than handed
    out, because a repair turn on a finding doctor no longer raises is a turn spent
    confirming there is nothing to do — and a blocked one is a gate asking the operator
    about a finding that is gone (`settle_stale_rows`).

    **An attempt is counted only against the node the turn left.** `repo_root` lets the
    close store `closed_digest` — `repair_scope_digest` of the row's scope as the turn left
    it — and lets a requeue compare that to the scope now. A finding still standing over an
    unchanged scope is the turn's repair failing, and costs an attempt. A finding standing
    over a *changed* scope says nothing about that turn: a sibling repair rewrote the node,
    a human edited it, or the run moved to another checkout of the book — and the verdict
    the row carries is about text that no longer exists. That reopen is free, and the stale
    verdict is dropped so no block can quote it. Each free reopen needs a real change to the
    scope by something other than this row's own turn, and those writers are bounded rows
    themselves, so the per-target bound still holds. A row closed with no digest — before
    this existed, or by a caller without `repo_root` — is counted as before.
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

    closing = [row for row in [current, *(batch or [])] if row]
    closed = {(_norm(row.get("kind")), _norm(row.get("target"))) for row in closing}
    for row in closing:
        logger.info(
            "marking item '%s' (%s) done%s",
            row.get("target", "?"), row.get("kind", "?"),
            f" ({doc_status})" if doc_status else "",
        )
    if closed:
        for i in items:
            if (_norm(i.get("kind")), _norm(i.get("target"))) in closed:
                i["status"] = "done"
                if repo_root and (sealed := repair_scope_digest(
                        repo_root, str(i.get("context", "")))):
                    i["closed_digest"] = sealed
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
            if (d.get("requeue") is True and existing.get("status") == "done"
                    and reopen_row(logger, existing, d, repo_root, max_attempts)):
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

    settled = 0
    if settle_fix_items:
        settled = settle_stale_rows(items, discovered or [], where="at the checkpoint")
        if settled:
            logger.info("closed %d pending repair item(s) whose finding stopped firing", settled)

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
        settled=settled,
        blocked=blocked,
        blocked_count=len(blocked),
    )


def last_added_counts(worklist_path: Path, count: int) -> dict[str, int]:
    """Kind breakdown of the last ``count`` items appended to *worklist_path*.

    ``record`` writes ``discovered`` items to the end of the worklist; this
    helper reads that tail and returns a ``{kind: n}`` summary. The audit's
    gate body uses it to say "5 behavior-repair, 2 reground:no-source at the
    bottom of <worklist>" without enumerating each row — the operator opens
    the worklist to see what was queued.

    Reading is the worklist's own JSON; no separate state. ``count`` is the
    number returned by ``Recorded.added`` from the ``record`` call that just
    ran, so this helper reads exactly the rows that call appended.
    """
    if count <= 0:
        return {}
    try:
        data = json.loads(Path(worklist_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    items = data.get("items", [])
    recent = items[-count:] if count <= len(items) else items
    return dict(Counter(str(item.get("kind", "")) for item in recent))


__all__ = [
    "MAX_TARGET_ATTEMPTS",
    "book_has_docs",
    "last_added_counts",
    "load_worklist",
    "record",
    "repair_keys",
    "select_item",
    "doctor_row",
    "settle_stale_rows",
]
