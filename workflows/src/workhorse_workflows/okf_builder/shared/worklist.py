"""The drain's two primitives: take an item, and write back what came of it."""
from __future__ import annotations

import hashlib
import json
import logging
import posixpath
from collections import Counter
from pathlib import Path
from typing import Any

from ostler import markdown
from ostler.model import document_anchors
from workhorse import worklist as wl
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Pick, Recorded


MAX_TARGET_ATTEMPTS = 3


MAX_BATCH_FINDINGS = 25

MAX_BATCH_FILES = 5


def _norm(s: object) -> str:
    return " ".join(str(s or "").split()).strip().lower()


def book_has_docs(features: Path) -> bool:
    """Whether this book has ever been written — one markdown file anywhere under it."""
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
    """Whether a worklist row is a doctor finding's repair — the only rows doctor may settle."""
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
    """Close every open doctor repair row doctor no longer reports."""
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
    features_root: str = "",
) -> bool:
    """Reopen a `done` row whose finding still stands; True when it went back to `pending`."""
    prior = ""
    sealed = str(existing.pop("closed_digest", "") or "")
    moved = bool(sealed and repo_root) and sealed != repair_scope_digest(
        repo_root, str(existing.get("context", "")), str(existing.get("target", "")),
        features_root,
    )
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
    """The one book file a repair row is about, and its findings — or None if it has none."""
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
    """The rows one repair turn takes: `first`, the open repair rows on its file, then on its sibling files."""
    scope = _repair_scope(rows[first])
    if scope is None:
        return [first]
    path, findings = scope
    taken, total, files = [first], len(findings), [path]
    open_scopes = [
        (n, other) for n, row in enumerate(rows)
        if n != first and row.get("status") in ("active", "pending")
        and (other := _repair_scope(row)) is not None
    ]
    folder = posixpath.dirname(path)
    same_file = [(n, o) for n, o in open_scopes if o[0] == path]
    siblings = [(n, o) for n, o in open_scopes
                if o[0] != path and posixpath.dirname(o[0]) == folder]
    for n, (other_path, other_findings) in [*same_file, *siblings]:
        if total + len(other_findings) > MAX_BATCH_FINDINGS:
            continue
        if other_path not in files:
            if len(files) >= MAX_BATCH_FILES:
                continue
            files.append(other_path)
        taken.append(n)
        total += len(other_findings)
    return taken


def _batch_context(rows: list[dict[str, Any]]) -> str:
    """One repair context over several rows: every node, code and finding."""
    contexts = [json.loads(str(r.get("context", ""))) for r in rows]
    findings = [f for c in contexts for f in (c.get("findings") or [])]
    paths = list(dict.fromkeys(str(c["path"]) for c in contexts))
    order = {p: i for i, p in enumerate(paths)}
    scope: dict[str, Any] = {"path": paths[0]} if len(paths) == 1 else {"paths": paths}
    return json.dumps({
        **scope,
        "nodes": list(dict.fromkeys(str(c.get("node", "")) for c in contexts)),
        "codes": list(dict.fromkeys(str(r.get("kind", "")).removeprefix("fix:") for r in rows)),
        "grounded": any(c.get("grounded") is True for c in contexts),
        "findings": sorted(findings, key=lambda f: (
            order.get(str(f.get("path", "")), 0), int(f.get("line", 0) or 0))),
    }, indent=2)


@blueprint.node
def select_item(
    logger: logging.Logger,
    worklist_path: str,
    max_items: int = 0,
    done_baseline: int = 0,
) -> Pick:
    """Pop the next pending item and mark it active."""
    path = Path(worklist_path)
    data = json.loads(path.read_text())
    items = [wl.WorkItem.model_validate(row) for row in data.get("items", [])]
    snap = wl.snapshot(items)
    done = snap.counts.done
    this_run = max(0, done - min(done_baseline, done))
    logger.info(
        "worklist %s: %d items, %d done (%d this run, baseline %d), cap %s",
        path, len(items), done, this_run, done_baseline, max_items or "none",
    )

    pick = wl.select_next(items)
    if pick is None:
        logger.info("drain is dry — no active or pending items; handing off to checkpoint")
        return Pick(
            done_count=done,
            done_this_run=this_run,
            progress=snap.progress,
            kinds=snap.kinds,
        )

    if max_items and this_run >= max_items:
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
    data["items"] = rows
    path.write_text(json.dumps(data, indent=2))
    pend = wl.counts(items).pending
    target = str(getattr(pick, "target", "") or "")
    batch = [rows[n] for n in taken]
    kinds = [str(r.get("kind", "")) for r in batch]
    codes = list(dict.fromkeys(k.removeprefix("fix:") for k in kinds if k.startswith("fix:")))
    logger.info(
        "picked %s item '%s' (%s)%s, %d still pending",
        "resumed active" if resumed else "next pending",
        target or "?", pick.kind or "?",
        f" with {len(batch) - 1} more row(s) on its file and its siblings"
        if len(batch) > 1 else "",
        pend,
    )
    return Pick(
        has_item=True,
        current_item=batch[0],
        batch=batch[1:],
        item_kind=pick.kind,
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
    """The lines a node owns in one document, or None when the document has no such node."""
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


def repair_scope_digest(
    repo_root: str, context: str, target: str = "", features_root: str = "",
) -> str:
    """A fingerprint of the book text a repair item is about, as it stands on disk now."""
    try:
        ctx = json.loads(context) if context else {}
    except json.JSONDecodeError:
        ctx = None
    if isinstance(ctx, dict) and ctx.get("node") and ctx.get("path"):
        scoped = True
        members = [str(ctx["node"])]
    elif isinstance(ctx, dict) and ctx.get("related"):
        scoped = True
        members = [str(m) for m in ctx.get("related") or []]
    elif target:
        scoped = False
        members = [target]
    else:
        return ""
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
    if not scoped and features_root:
        try:
            waivers = paths.waivers_path(features_root).read_text(encoding="utf-8")
        except OSError:
            waivers = "\1absent"
        digest.update(waivers.encode())
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
    features_root: str = "",
    batch: list[dict[str, Any]] | None = None,
) -> Recorded:
    """Mark the current item done, merge newly-discovered items, and count the re-tries."""
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
                        repo_root, str(i.get("context", "")), str(i.get("target", "")),
                        features_root,
                )):
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
                    and reopen_row(logger, existing, d, repo_root, max_attempts, features_root)):
                added += 1
            continue
        items.append({
            "kind": d["kind"], "target": d["target"],
            "context": d.get("context", ""), "status": "pending",
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
    """Kind breakdown of the last ``count`` items appended to *worklist_path*."""
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
