"""Adjudication: give a blocked finding a side, from the other layer.

`ostler doctor` reads the book. A finding of the collision class — `ambiguous-locator`,
`unnamed-interactive`, a `missing-code-symbol` on a citation the source no longer carries —
is a claim about the *correspondence* of two representations, and a checker reading one
of them cannot say which is wrong. **Fault cannot be assigned from one side of a
correspondence.** The repair turn, which also only edits the book, spends its attempts
and the row blocks. This module is the observation of the other side.

Three nodes, each mechanical:

* `blocked_rows` — the rows at the attempt limit that no verdict has touched yet;
* `gather_evidence` — the finding, the covering story (the `Story:` trailer on the latest
  commit over the node's `code:` targets, via `story-for-node`) and its text, and the
  code refs the turn must open. The story is the spec; no story means the code is the
  intent by construction;
* `apply_verdict` — the routing. `book` returns the row to the drain with a fresh
  allowance and the chain in its context. `code` files a seed in the covering story's
  epic — else the invariant epic — and writes a `known-defect:` bullet naming it on each
  node the finding raised, which is the record doctor takes back the moment the seed
  closes or the finding stops firing. `story` records the conflict on the story so doctor
  raises `story-conflict`, and leaves the row blocked for the operator gate: rewriting
  intent is not the adjudicator's to do.

Nothing here is excused. A `code` verdict on a node that cannot carry the record files the
seed and leaves the row blocked with the chain, so the gate says what was decided and the
finding stays in doctor's report until the seed lands.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ostler import Ostler, crud, registry
from ostler.doctor import parse_known_defect

from workhorse_workflows.okf_builder.shared import blueprint
from workhorse_workflows.okf_builder.shared.schemas import (
    Applied,
    BlockedRows,
    Evidence,
)

#: Where a `code` verdict files its seed when no story covers the node. A repo-wide
#: invariant — the accessibility rules first among them — holds without a story stating
#: it, and a violation of one is a code defect wherever it appears.
INVARIANT_EPIC = "invariant-code-defects"
INVARIANT_EPIC_TITLE = "Code defects against repo-wide invariants, found by the book"

VERDICTS = ("book", "code", "story")


def _context(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("context", "")
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _nodes_of(context: dict[str, Any]) -> list[str]:
    """Every node a repair item names: `node` on a per-node item, `related` on a group."""
    related = context.get("related")
    if isinstance(related, list) and related:
        return [str(n) for n in related if n]
    node = str(context.get("node") or "")
    path = str(context.get("path") or "")
    if node and path and node != path and not node.startswith(path):
        return [f"{path}#{node}"]
    return [node or path] if (node or path) else []


def _resolve(okf: Ostler, node_id: str) -> str:
    """The UI node id a repair item's `path#node` addresses.

    The checkpoint cuts a doctor ref after its node segment, and on a *file* node — whose
    id is the bare path — that segment is a member (`…#verify`), not a node. The file is
    the node then, and it is what the join and the bullet must address.
    """
    if okf.graph.find_ui_node(node_id) is not None:
        return node_id
    path = node_id.partition("#")[0]
    return path if okf.graph.find_ui_node(path) is not None else node_id


@blueprint.node
def blocked_rows(logger: logging.Logger, worklist_path: str = "") -> BlockedRows:
    """The blocked rows still waiting for a side — a row already adjudicated keeps its
    verdict until the operator's answer clears it, so one finding is judged once per gate."""
    data = json.loads(Path(worklist_path).read_text())
    rows = [
        i for i in data.get("items", [])
        if i.get("status") == "blocked" and not i.get("verdict")
    ]
    logger.info("%d blocked row(s) await adjudication", len(rows))
    return BlockedRows(rows=rows, count=len(rows))


@blueprint.node
def gather_evidence(
    logger: logging.Logger,
    repo_root: str = "",
    source_root: str = "",
    row_json: str = "",
) -> Evidence:
    """Read the other side: the story the node's code was last written to, and its text."""
    row = json.loads(row_json or "{}")
    context = _context(row)
    nodes = _nodes_of(context)
    okf = Ostler(repo_root)
    story: dict[str, Any] | None = None
    resolved = False
    warnings: list[str] = []
    code_refs: list[str] = []
    seen_refs: set[str] = set()
    for node in nodes:
        rows = okf.query("story-for-node", _resolve(okf, node), checkouts={"source": source_root})
        if not rows:
            warnings.append(f"{node}: not a UI node — no `code:` join to a story")
            continue
        found = rows[0]
        for ref in found.get("node", {}).get("codeRefs", []) or []:
            if ref not in seen_refs:
                seen_refs.add(ref)
                code_refs.append(str(ref))
        warnings.extend(str(w) for w in found.get("warnings", []) or [])
        if story is None and found.get("story"):
            story = dict(found["story"])
            resolved = bool(found.get("resolved"))
    text = ""
    if story is not None and resolved:
        located = okf.graph.find_story(str(story.get("slug") or story.get("id") or ""))
        if located is not None and located[1].story_md is not None:
            text = located[1].story_md.read_text(encoding="utf-8")
    logger.info(
        "evidence for %s: %d node(s), story %s",
        row.get("target"), len(nodes), (story or {}).get("id") or "none (code is the intent)",
    )
    return Evidence(
        target=str(row.get("target", "")),
        kind=str(row.get("kind", "")),
        code=str(context.get("code") or str(row.get("kind", "")).removeprefix("fix:")),
        nodes=nodes,
        findings=[f for f in context.get("findings", []) if isinstance(f, dict)],
        code_refs=code_refs,
        story=story,
        story_text=text,
        story_resolved=resolved,
        warnings=warnings,
        blocked_reason=str(row.get("blocked_reason", "")),
    )


def _bullet_line(seed: str, code: str, reason: str) -> str:
    text = " ".join(reason.split()) or "adjudicated as a code defect"
    return f"- known-defect: {seed} {code} — {text}"


def _bullet_slot(lines: list[str], heading_line: int) -> int:
    """Where the node's bullet block ends: the index right after its last `- ` line.

    `heading_line` is 1-based, so it doubles as the index of the line after the heading.
    The block is the first run of bullets (with their indented continuations) after the
    heading, blank lines before it skipped; a node with no bullets gets the record right
    under its heading.
    """
    i = heading_line
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or not lines[i].startswith("- "):
        return heading_line
    while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  ")):
        i += 1
    return i


def _mark_node(okf: Ostler, node_id: str, seed: str, code: str, reason: str) -> bool:
    """Write the `known-defect:` bullet under a UI node. False when the node carries none."""
    node = okf.graph.find_ui_node(_resolve(okf, node_id))
    if node is None or "known-defect" not in registry.declared_keys(node.type):
        return False
    lines = node.path.read_text(encoding="utf-8").splitlines()
    present = node.meta.get("known-defect") or []
    for value in present if isinstance(present, list) else [present]:
        if parse_known_defect(str(value).strip()) == (seed, code):
            return True
    lines.insert(_bullet_slot(lines, node.line), _bullet_line(seed, code, reason))
    node.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _ensure_epic(okf: Ostler, name: str, title: str) -> str:
    created = okf.create_epic(name, title)
    if created.ok:
        okf.todo_add(name)
    return name


def _write_rows(worklist_path: str, update: Any) -> None:
    path = Path(worklist_path)
    data = json.loads(path.read_text())
    for row in data.get("items", []):
        update(row)
    path.write_text(json.dumps(data, indent=2))


@blueprint.node
def apply_verdict(
    logger: logging.Logger,
    repo_root: str = "",
    worklist_path: str = "",
    row_json: str = "",
    verdict: str = "",
    chain: str = "",
    seed_summary: str = "",
    story_slug: str = "",
    story_epic: str = "",
) -> Applied:
    """Route one verdict. Every branch writes the verdict and the chain on the row."""
    row = json.loads(row_json or "{}")
    target = str(row.get("target", ""))
    kind = str(row.get("kind", ""))
    context = _context(row)
    code = str(context.get("code") or kind.removeprefix("fix:"))
    nodes = _nodes_of(context)
    if verdict not in VERDICTS:
        raise ValueError(f"adjudication of {target!r} returned no verdict: {verdict!r}")

    applied = Applied(verdict=verdict, target=target)
    okf = Ostler(repo_root)

    if verdict == "code":
        summary = " ".join(seed_summary.split()) or f"{code} on {', '.join(nodes)}"
        epic = story_epic or _ensure_epic(okf, INVARIANT_EPIC, INVARIANT_EPIC_TITLE)
        seed = okf.allocate_id()
        result = crud.add_seed(
            Ostler(repo_root).graph, epic, seed, status=registry.DEFAULT_SEED_STATUS,
            summary=summary, meta={"sourceBullet": f"{target} — {chain}"},
        )
        if not result.ok:
            raise RuntimeError(f"could not file seed {seed} in {epic}: {result.message}")
        fresh = Ostler(repo_root)
        marked = [n for n in nodes if _mark_node(fresh, n, seed, code, summary)]
        applied.seed, applied.epic, applied.marked = seed, epic, marked
        logger.info(
            "%s: code is the side at fault — seed %s in %s, known-defect on %d node(s)",
            target, seed, epic, len(marked), extra={"activity": True},
        )
    elif verdict == "story" and story_slug:
        result = okf.set_conflict(story_slug, chain)
        if not result.ok:
            raise RuntimeError(f"could not record the conflict on {story_slug}: {result.message}")
        applied.story = story_slug
        logger.warning("%s: the story is at fault — conflict recorded on %s", target, story_slug)
    elif verdict == "story":
        logger.warning("%s: `story` verdict with no covering story — left for the operator", target)
    else:
        applied.requeued = True
        logger.info("%s: the book is the side at fault — back to the drain", target)

    def update(item: dict[str, Any]) -> None:
        if (item.get("kind"), item.get("target")) != (kind, target):
            return
        item["verdict"] = verdict
        item["chain"] = chain
        if applied.seed:
            item["seed"] = applied.seed
        if applied.requeued:
            item["status"] = "pending"
            item["attempts"] = 0
            item.pop("blocked_reason", None)
            item["context"] = json.dumps({**context, "adjudication": chain})
        elif applied.marked and set(applied.marked) == set(nodes):
            # Every node the finding raised now carries the record; doctor drops the
            # finding on the next checkpoint, so the row is closed like any other repair.
            item["status"] = "done"
            item["doc_status"] = "code-defect"
            item["note"] = f"seed {applied.seed} filed; known-defect on {', '.join(nodes)}"
        # Otherwise the row stays blocked as it was: `blocked_reason` keeps the repair
        # turn's own sentence, and the gate prints the verdict, the seed and the chain
        # from the fields written above.

    _write_rows(worklist_path, update)
    return applied


__all__ = [
    "INVARIANT_EPIC",
    "INVARIANT_EPIC_TITLE",
    "VERDICTS",
    "apply_verdict",
    "blocked_rows",
    "gather_evidence",
]
