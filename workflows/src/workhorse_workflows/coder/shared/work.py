"""The run's worklist: the stories, follow-ups and findings it works, and who may move each."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from workhorse import worklist as wl
from workhorse.pyflow import WorkflowFailed

WORKLIST_FILE = "worklist.json"
ANSWER_LOG = "answers.md"

STORY = "story"
FOLLOW_UP = "follow-up"
FINDING = "finding"
PROGRESS_KINDS = frozenset({STORY, FOLLOW_UP})

PENDING = "pending"
ACTIVE = "active"
DONE = "done"
OPEN = "open"
SETTLED = "settled"
DECLINED = "declined"

SCHEME = wl.Scheme(
    done=frozenset({DONE, SETTLED, DECLINED}),
    active=frozenset({ACTIVE}),
    blocked=frozenset(),
)

FILERS: dict[str, frozenset[str]] = {
    STORY: frozenset({"launch", "amendment"}),
    FOLLOW_UP: frozenset({"dev"}),
    FINDING: frozenset({"review", "qa"}),
}

MOVERS: dict[str, frozenset[str]] = {
    STORY: frozenset({"standing"}),
    FOLLOW_UP: frozenset({"standing"}),
    FINDING: frozenset({"settlement"}),
}


def worklist_path(run_dir: str | Path) -> Path:
    """Where the run keeps its worklist."""
    return Path(run_dir) / WORKLIST_FILE


def answer_log_path(run_dir: str | Path) -> Path:
    """Where the run keeps every operator question and its answer."""
    return Path(run_dir) / ANSWER_LOG


def worklist(run_dir: str | Path) -> wl.WorkList:
    """The run's one worklist, under the coder's status scheme."""
    return wl.WorkList(wl.JsonBackend(worklist_path(run_dir)), SCHEME)


def _check(table: dict[str, frozenset[str]], kind: str, by: str, verb: str) -> None:
    allowed = table.get(kind, frozenset())
    if by not in allowed:
        raise WorkflowFailed(
            f"{by!r} may not {verb} {kind!r} items; only {sorted(allowed)} may"
        )


def file(work: wl.WorkList, items: Iterable[wl.WorkItem], *, by: str) -> list[wl.WorkItem]:
    """File new items, skipping any already filed with the same content."""
    stored = {it.id: it for it in work.items()}
    fresh: list[wl.WorkItem] = []
    for it in items:
        _check(FILERS, it.kind, by, "file")
        known = stored.get(it.id)
        if known is None:
            fresh.append(it)
            continue
        if known.digest != wl.payload_digest(it):
            raise WorkflowFailed(
                f"work item {it.id!r} was filed again with different content"
            )
    return work.add(fresh)


def move(
    work: wl.WorkList, ids: Iterable[str], status: str, *, kind: str, by: str
) -> int:
    """Set the status of the named items of one kind, on behalf of an allowed mover."""
    _check(MOVERS, kind, by, "move")
    return work.settle(ids, status, kind)


def find(work: wl.WorkList, item_id: str) -> wl.WorkItem | None:
    """One item by id, of any kind."""
    return next((it for it in work.items() if it.id == item_id), None)


def story_items(entries: Sequence[dict[str, Any]], start: float = 0.0, stop: float | None = None) -> list[wl.WorkItem]:
    """Story items for ostler's story entries, spread over the order gap they are filed into."""
    step = 1.0 if stop is None else (stop - start) / (len(entries) + 1)
    return [
        wl.WorkItem(
            id=str(entry["slug"]),
            kind=STORY,
            status=PENDING,
            order=start + step * (i + 1),
            payload={
                "epic": str(entry.get("epic") or ""),
                "story_id": str(entry.get("id") or ""),
            },
        )
        for i, entry in enumerate(entries)
    ]


def amend(work: wl.WorkList, epic: str, entries: Sequence[dict[str, Any]]) -> list[wl.WorkItem]:
    """Re-file one epic's stories after a replan, keeping the ones already done."""
    progress = work.items(PROGRESS_KINDS)
    ours = [it for it in progress if it.payload.get("epic") == epic]
    for it in ours:
        if it.kind == STORY and it.status not in SCHEME.done:
            work.prune(it.id, STORY)
    kept = {it.id for it in work.items(STORY)}
    wanted = [entry for entry in entries if str(entry["slug"]) not in kept]
    first = min((it.order or 0 for it in ours), default=None)
    settled = [it.order or 0 for it in ours if it.status in SCHEME.done]
    before = [it.order or 0 for it in progress if it.payload.get("epic") != epic
              and first is not None and (it.order or 0) < first]
    start = max(settled, default=max(before, default=0.0))
    later = [it.order or 0 for it in progress if it.payload.get("epic") != epic
             and (it.order or 0) > start]
    stop = min(later, default=None)
    if stop is None:
        stop = max((it.order or 0 for it in progress), default=start) + len(wanted) + 1
    return file(work, story_items(wanted, start, stop), by="amendment")


def follow_up_items(
    work: wl.WorkList, parent: wl.WorkItem, follow_ups: Sequence[dict[str, str]]
) -> list[wl.WorkItem]:
    """Follow-up items for `parent`, ordered after it and its earlier follow-ups."""
    progress = work.items(PROGRESS_KINDS)
    family = [it.order or 0 for it in progress
              if it.id == parent.id or it.payload.get("parent") == parent.id]
    start = max(family, default=parent.order or 0)
    later = [it.order or 0 for it in progress if (it.order or 0) > start]
    stop = min(later, default=start + len(follow_ups) + 1)
    step = (stop - start) / (len(follow_ups) + 1)
    items: list[wl.WorkItem] = []
    for i, entry in enumerate(follow_ups):
        title = entry.get("title", "").strip()
        reason = entry.get("reason", "").strip()
        key = hashlib.sha256(f"{title}\n{reason}".encode()).hexdigest()[:8]
        items.append(wl.WorkItem(
            id=f"{parent.id}/follow-up-{key}",
            kind=FOLLOW_UP,
            status=PENDING,
            order=start + step * (i + 1),
            payload={
                "parent": parent.id,
                "epic": str(parent.payload.get("epic") or ""),
                "story_id": str(parent.payload.get("story_id") or ""),
                "title": title,
                "reason": reason,
            },
        ))
    return items


def story_of(item: wl.WorkItem) -> str:
    """The story slug an item's work belongs to: its own id, or its parent's."""
    return str(item.payload.get("parent") or item.id)


def findings_of(work: wl.WorkList, work_id: str) -> list[wl.WorkItem]:
    """Every finding item filed against one work item."""
    return [it for it in work.items(FINDING) if it.payload.get("work_id") == work_id]


def next_round(work: wl.WorkList, work_id: str, source: str) -> int:
    """One past the highest round `source` has filed against `work_id`."""
    rounds = [int(it.payload.get("round") or 0) for it in findings_of(work, work_id)
              if it.payload.get("source") == source]
    return max(rounds, default=0) + 1


def round_filed(work: wl.WorkList, work_id: str, source: str, number: int) -> bool:
    """Whether `source` already filed round `number` against `work_id`."""
    return any(
        it.payload.get("source") == source and int(it.payload.get("round") or 0) == number
        for it in findings_of(work, work_id)
    )


def finding_items(
    work_id: str, source: str, number: int, findings: Sequence[dict[str, Any]]
) -> list[wl.WorkItem]:
    """Finding items for one round of one source, numbered in the order it reported them."""
    return [
        wl.WorkItem(
            id=f"{work_id}/{source}-{number}.{i + 1}",
            kind=FINDING,
            status=OPEN,
            payload={
                "work_id": work_id,
                "source": source,
                "round": number,
                "target": str(entry.get("target") or ""),
                "issue": str(entry.get("issue") or ""),
                "repair": str(entry.get("repair") or ""),
                "category": str(entry.get("category") or ""),
                "score": int(entry.get("score") or 0),
            },
        )
        for i, entry in enumerate(findings)
    ]


def open_findings(work: wl.WorkList, work_id: str = "") -> list[wl.WorkItem]:
    """Finding items not yet settled or declined, for one work item or for the whole run."""
    return [
        it for it in work.items(FINDING)
        if it.status not in SCHEME.done and (not work_id or it.payload.get("work_id") == work_id)
    ]


def epic_done(work: wl.WorkList, epic: str) -> bool:
    """Whether every story and follow-up of `epic` is done."""
    return all(
        it.status in SCHEME.done
        for it in work.items(PROGRESS_KINDS)
        if it.payload.get("epic") == epic
    )


def progress(work: wl.WorkList, current: str | None = None) -> wl.WorkSnapshot:
    """How far the run is through its stories and follow-ups."""
    return work.snapshot(current, PROGRESS_KINDS)


def log_answer(run_dir: str | Path, heading: str, text: str) -> None:
    """Append one operator answer to the run's answer log."""
    path = answer_log_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"## {heading}\n\n{text.strip()}\n\n")


def _finding_line(it: wl.WorkItem) -> str:
    target = it.payload.get("target") or "(no target)"
    return f"- `{it.id}` ({it.status}): `{target}`: {it.payload.get('issue') or ''}"


def resume_note(run_dir: str | Path, work_id: str, story_path: str, spec_dir: str) -> str:
    """Where this work stands, rendered so a fresh session can pick it up with nothing else."""
    work = worklist(run_dir)
    snap = progress(work, work_id)
    item = find(work, work_id)
    lines = [
        "## Resume note",
        "",
        f"You are the dev owner for `{work_id}`. This note is the run's state, read from disk.",
        f"- worklist: `{worklist_path(run_dir)}` (read it again whenever you lose track)",
        f"- answer log: `{answer_log_path(run_dir)}`",
        f"- story: `{story_path}`",
        f"- spec dir: `{spec_dir}`",
        f"- progress: {snap.progress} items done",
        "",
    ]
    if item is not None and item.kind == FOLLOW_UP:
        lines += [
            "### This follow-up",
            "",
            f"{item.payload.get('title') or ''}",
            "",
            f"{item.payload.get('reason') or ''}",
            "",
        ]
    filed = [it for it in work.items(FOLLOW_UP) if it.payload.get("parent") == work_id]
    if filed:
        lines += ["### Follow-ups already filed", ""]
        lines += [f"- `{it.id}` ({it.status}): {it.payload.get('title') or ''}" for it in filed]
        lines.append("")
    findings = findings_of(work, work_id)
    if findings:
        lines += ["### Findings filed against this work", ""]
        lines += [_finding_line(it) for it in findings]
        lines.append("")
    log = answer_log_path(run_dir)
    if log.is_file():
        lines += ["### Operator answers so far", "", log.read_text(encoding="utf-8").strip(), ""]
    return "\n".join(lines).rstrip() + "\n"


__all__ = [
    "ACTIVE",
    "ANSWER_LOG",
    "DECLINED",
    "DONE",
    "FILERS",
    "FINDING",
    "FOLLOW_UP",
    "MOVERS",
    "OPEN",
    "PENDING",
    "PROGRESS_KINDS",
    "SCHEME",
    "SETTLED",
    "STORY",
    "WORKLIST_FILE",
    "amend",
    "answer_log_path",
    "epic_done",
    "file",
    "find",
    "finding_items",
    "findings_of",
    "follow_up_items",
    "log_answer",
    "move",
    "next_round",
    "open_findings",
    "progress",
    "resume_note",
    "round_filed",
    "story_items",
    "story_of",
    "worklist",
    "worklist_path",
]
