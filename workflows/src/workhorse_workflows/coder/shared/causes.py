"""Cause identity: which reports describe one defect, who owns each cause, and where a defect escaped from."""
from __future__ import annotations

import logging
import re
from collections.abc import Collection, Mapping, Sequence
from typing import Any

from workhorse import worklist as wl
from workhorse.pyflow import Workflow

from workhorse_workflows.coder.shared import work
from workhorse_workflows.coder.shared.judge import (
    JUDGE_PROFILE,
    Judge,
    Question,
    ReadingJudge,
    Ruling,
    RuleJudge,
    Tiered,
    accepting,
    answer_of,
    judge_args,
)

STOP_WORDS = frozenset({"a", "an", "and", "the", "of", "to", "for", "in", "on", "when", "with", "or"})
NEW = "new"
NONE = "none"
TITLE_CAP = 90


def words(text: str) -> frozenset[str]:
    """The lowercase alphanumeric words of `text`, without the small words that carry no cause."""
    return frozenset(re.split(r"[^a-z0-9]+", text.lower())) - STOP_WORDS - {""}


def cause_rule(question: Question) -> Ruling:
    """Match each subject to the first context entry that has exactly its words."""
    answers: dict[str, str] = {}
    for subject, text in question.subjects.items():
        key = words(text)
        hit = next((cid for cid, known in question.context.items() if words(known) == key), None)
        if hit is not None:
            answers[subject] = hit
    return Ruling(answers=answers)


def cause_judge(flow: Workflow, power: str) -> Judge:
    """The word rule first, then one tool-less reading at `power` of what the rule left."""

    def read(question: Question) -> Ruling:
        return flow.agent(
            "shared/prompts/judge.md",
            returns=Ruling,
            power=power,
            profile=JUDGE_PROFILE,
            args=judge_args(question),
            accept=accepting(question),
        )

    return Tiered(RuleJudge({"cause": cause_rule}), ReadingJudge(read))


def cause_question(reports: Mapping[str, str], causes: Mapping[str, str]) -> Question:
    """Which known cause does each report describe, or none of them."""
    return Question(
        kind="cause",
        ask=(
            "Which known cause does each report describe? A report and a cause are one "
            "cause when a person using the app would see the same thing go wrong on the "
            "same screen. A different story, criterion number, trigger wording, evidence "
            "or proposed fix does not make it a different cause."
        ),
        subjects=dict(reports),
        context=dict(causes),
        answers=(*causes, NEW),
        default=NEW,
    )


def same_causes(judge: Judge, reports: Mapping[str, str], causes: Mapping[str, str]) -> dict[str, str]:
    """Each report id to the cause id it describes, or `new`."""
    if not reports or not causes:
        return {rid: NEW for rid in reports}
    question = cause_question(reports, causes)
    ruling = judge.rule(question)
    return {rid: answer_of(question, ruling, rid) for rid in reports}


def escape_question(reports: Mapping[str, str], stories: Mapping[str, str]) -> Question:
    """Which committed story's acceptance criteria does each defect break, or none."""
    return Question(
        kind="escape",
        ask="Which already committed story's acceptance criteria does each defect break?",
        subjects=dict(reports),
        context=dict(stories),
        answers=(*stories, NONE),
        default=NONE,
    )


def escaped_from(judge: Judge, reports: Mapping[str, str], stories: Mapping[str, str]) -> dict[str, str]:
    """Each report id to the committed story it escaped from, or an empty string."""
    if not reports or not stories:
        return {rid: "" for rid in reports}
    question = escape_question(reports, stories)
    ruling = judge.rule(question)
    found = {rid: answer_of(question, ruling, rid) for rid in reports}
    return {rid: "" if slug == NONE else slug for rid, slug in found.items()}


def open_causes(w: wl.WorkList, story: str) -> dict[str, str]:
    """The text of every cause still open under `story`: its pending or active follow-ups and its open findings."""
    causes = {
        it.id: str(it.payload.get("title") or "")
        for it in w.items(work.FOLLOW_UP)
        if it.payload.get("parent") == story and it.status in (work.PENDING, work.ACTIVE)
    }
    causes |= {it.id: str(it.payload.get("issue") or "") for it in work.open_findings(w, story)}
    return causes


def file_findings(
    judge: Judge,
    w: wl.WorkList,
    work_id: str,
    source: str,
    number: int,
    findings: Sequence[dict[str, Any]],
    *,
    by: str,
) -> list[wl.WorkItem]:
    """File one round of findings open, merging the older open finding of the same cause into the newest."""
    reports = {
        work.finding_id(work_id, source, number, i): str(entry.get("issue") or "")
        for i, entry in enumerate(findings)
    }
    known = {it.id: str(it.payload.get("issue") or "") for it in work.open_findings(w, work_id)}
    same = same_causes(judge, reports, known)
    taken: dict[str, str] = {}
    into: list[str] = []
    for rid in reports:
        old = same[rid]
        if old == NEW:
            into.append("")
        elif old in taken:
            into.append(taken[old])
        else:
            taken[old] = rid
            into.append("")
    filed = work.file(w, work.finding_items(work_id, source, number, findings, into), by=by)
    for old, rid in taken.items():
        stale = work.find(w, old)
        if stale is not None:
            work.replace(w, stale.model_copy(update={
                "payload": stale.payload | {"same_as": rid},
                "status": work.MERGED,
            }))
    return filed


def consolidate(w: wl.WorkList, logger: logging.Logger) -> list[str]:
    """Prune the follow-ups of one story that share a cause by words alone, keeping the active one or else the first."""
    groups: dict[tuple[str, frozenset[str]], list[wl.WorkItem]] = {}
    for it in sorted(w.items(work.FOLLOW_UP), key=lambda x: x.order or 0):
        if it.status in (work.PENDING, work.ACTIVE):
            key = (str(it.payload.get("parent") or ""), words(str(it.payload.get("title") or "")))
            groups.setdefault(key, []).append(it)
    pruned: list[str] = []
    for group in groups.values():
        keep = next((it for it in group if it.status == work.ACTIVE), group[0])
        for it in group:
            if it.id == keep.id:
                continue
            for finding in work.findings_of(w, it.id):
                work.replace(w, finding.model_copy(update={
                    "payload": finding.payload | {"work_id": keep.id},
                }))
            w.prune(it.id, work.FOLLOW_UP)
            pruned.append(it.id)
    if pruned:
        logger.info("consolidated %d follow-up(s) sharing a cause: %s", len(pruned), ", ".join(pruned))
    return pruned


def first_sentence(text: str) -> str:
    """The first sentence of `text`, capped at the longest a follow-up title may be."""
    return re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0][:TITLE_CAP]


def _group_findings(judge: Judge, held: Sequence[wl.WorkItem]) -> list[list[wl.WorkItem]]:
    """The findings split into groups that describe one cause each, the first of a group leading it."""
    groups: dict[str, list[wl.WorkItem]] = {}
    leaders: dict[str, str] = {}
    for it in held:
        issue = str(it.payload.get("issue") or "")
        hit = same_causes(judge, {it.id: issue}, leaders)[it.id]
        if hit == NEW:
            groups[it.id] = [it]
            leaders[it.id] = issue
        else:
            groups[hit].append(it)
    return list(groups.values())


def _reown(
    w: wl.WorkList,
    logger: logging.Logger,
    group: Sequence[wl.WorkItem],
    target: wl.WorkItem,
    origins: Mapping[str, str],
) -> None:
    """Hand a group of findings to `target`, one of them open and the rest merged into it, and record the escape."""
    leader = next((it.id for it in work.open_findings(w, target.id)), group[-1].id)
    origin = origins[group[0].id]
    for it in group:
        merged = it.id != leader
        payload = it.payload | {"work_id": target.id, "escaped_from": origins[it.id]}
        if merged:
            payload["same_as"] = leader
        work.replace(w, it.model_copy(update={
            "payload": payload,
            "status": work.MERGED if merged else it.status,
        }))
    if not target.payload.get("escaped_from"):
        work.replace(w, target.model_copy(update={
            "payload": target.payload | {"escaped_from": origin},
        }))
        logger.info("escape: %s found after %s committed", target.id, origin)


def own(
    judge: Judge,
    w: wl.WorkList,
    logger: logging.Logger,
    *,
    owners: Collection[str] | None = None,
    file_new: bool = True,
) -> int:
    """Hand the open findings of finished work to the follow-up that owns their cause, filing one when none does."""
    progress = {it.id: it for it in w.items(work.PROGRESS_KINDS)}
    if owners is None:
        owners = {wid for wid, it in progress.items() if it.status == work.DONE}
    held = [
        it for it in work.open_findings(w)
        if it.payload.get("work_id") in owners and it.payload.get("work_id") in progress
    ]
    moved = 0
    epic_of = {it.id: str(progress[str(it.payload["work_id"])].payload.get("epic") or "") for it in held}
    for epic in dict.fromkeys(epic_of.values()):
        mine = [it for it in held if epic_of[it.id] == epic]
        origins = {it.id: work.story_of(progress[str(it.payload["work_id"])]) for it in mine}
        targets = {
            fu.id: fu for fu in w.items(work.FOLLOW_UP)
            if fu.status in (work.PENDING, work.ACTIVE) and fu.id not in owners
            and str(fu.payload.get("epic") or "") == epic
        }
        same = same_causes(
            judge,
            {it.id: str(it.payload.get("issue") or "") for it in mine},
            {fid: str(fu.payload.get("title") or "") for fid, fu in targets.items()},
        )
        for fid, fu in targets.items():
            group = [it for it in mine if same[it.id] == fid]
            if group:
                _reown(w, logger, group, fu, origins)
                moved += len(group)
        if not file_new:
            continue
        unmatched = [it for it in mine if same[it.id] == NEW]
        for owner in dict.fromkeys(str(it.payload["work_id"]) for it in unmatched):
            held_by = [it for it in unmatched if it.payload["work_id"] == owner]
            parent = progress.get(work.story_of(progress[owner]), progress[owner])
            for group in _group_findings(judge, held_by):
                issue = str(group[0].payload.get("issue") or "")
                entry = {"title": first_sentence(issue), "reason": issue}
                made = work.follow_up_items(w, parent, [entry])
                target = work.find(w, made[0].id)
                if target is None:
                    work.file(w, made, by="ownership")
                    target = work.find(w, made[0].id)
                if target is not None:
                    _reown(w, logger, group, target, origins)
                    moved += len(group)
    return moved


__all__ = [
    "NEW",
    "NONE",
    "cause_judge",
    "cause_question",
    "cause_rule",
    "consolidate",
    "escape_question",
    "escaped_from",
    "file_findings",
    "first_sentence",
    "open_causes",
    "own",
    "same_causes",
    "words",
]
