"""The coder→author edge: drain separate-scope discoveries into the repo backlog.

Ports `append-backlog-item.py`. When implement, review or QA finds work that is genuinely
*separate* scope, it writes the item to `<spec_dir>/backlog-items.json`; this node appends
it to `docs/backlog.md` so the author workflow authors it next run. A coder-filed `[id]` is
a valid owner for a `deferred` gap, which is how the author's coverage gate resolves and
the loop closes.

The guardrail that keeps this from becoming a dumping ground lives in the prompts, not
here: a buildable in-scope precondition is *built* by the implementer, never punted.

Nothing changes about the filing rules — the three de-dup signals, the section placement,
the backlog scaffold, the reconciled-items unlink and the best-effort degradation are all
as written. What changes is what a failure does: the script printed a note to stderr and
carried on, and a node logs it, because a run record that names the node is the whole point
of having one.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from workhorse.scriptutil import find_docs_root
from workhorse_workflows.coder.nodes._blueprint import blueprint
from workhorse_workflows.coder.schemas.qa import BacklogDrain

#: The backlog's bullet grammar: `- [kebab-id] one self-contained line`.
BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")

#: Where an item lands when it names no section of its own, created once per backlog.
FILED_HEADING = "## Filed by coder"

#: A trailing `(blocked: …)` annotation is `mark-fix-blocked.py`'s, not part of the item's
#: identity — stripped before comparing descriptions so a re-file still de-dups against it.
BLOCKED_SUFFIX_RE = re.compile(r"\s*\(blocked\b.*$", re.IGNORECASE)

#: The backlog itself. Repo-relative: the node joins it onto a freshly resolved docs root.
BACKLOG_REL = "docs/backlog.md"


def kebab(raw: str) -> str:
    """Sanitize an id to a stable kebab handle (the backlog's `[id]` grammar)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw).strip().lower()).strip("-")


def norm_desc(desc: str) -> str:
    """Normalize a description to an identity key; empty means "never matches"."""
    text = BLOCKED_SUFFIX_RE.sub("", str(desc or ""))
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def id_token_set(item_id: str) -> frozenset[str]:
    """The tokens of a kebab id, order-insensitive, so a word-permuted re-file collides."""
    return frozenset(t for t in re.split(r"[.\-_]+", str(item_id or "").lower()) if t)


class Seen:
    """The three high-precision de-dup signals, seeded from the backlog and grown per batch.

    All three are exact matches, not fuzzy, and that is the trade the script chose
    deliberately: two items that merely share some words are *not* merged, because dropping
    genuinely-separate scope is worse than filing a near-duplicate — the author's coverage
    gate depends on filed items existing.
    """

    def __init__(self, lines: list[str]) -> None:
        self.ids: set[str] = set()
        self.descs: set[str] = set()
        self.idsets: set[frozenset[str]] = set()
        for line in lines:
            match = BACKLOG_ID_RE.match(line)
            if match:
                self.add(match.group(1), match.group(2))

    def add(self, item_id: str, desc: str) -> None:
        """Record an item so the rest of the batch de-dups against it too."""
        if item_id:
            self.ids.add(item_id)
            tokens = id_token_set(item_id)
            if tokens:
                self.idsets.add(tokens)
        key = norm_desc(desc)
        if key:
            self.descs.add(key)

    def duplicate(self, item_id: str, desc: str) -> bool:
        """Same id, same id-token-set, or same normalized description."""
        if item_id and item_id in self.ids:
            return True
        tokens = id_token_set(item_id)
        if tokens and tokens in self.idsets:
            return True
        key = norm_desc(desc)
        return bool(key and key in self.descs)


def _load_items(logger: logging.Logger, items_path: Path) -> list[dict[str, Any]]:
    """The filed items, or `[]` — an unreadable or malformed file is a logged no-op."""
    if not items_path.is_file():
        return []
    try:
        data = json.loads(items_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("items file unreadable: %s", exc)
        return []
    if isinstance(data, dict):
        data = data.get("items") or []
    return [item for item in data if isinstance(item, dict)]


def _insert_under_section(lines: list[str], section: str, bullet: str) -> list[str]:
    """Append `bullet` to the named `## section`, or under `## Filed by coder` at the end."""
    if section:
        target = section.strip().lstrip("#").strip().lower()
        for index, line in enumerate(lines):
            if line.lstrip().startswith("#") and line.lstrip("#").strip().lower() == target:
                end = index + 1
                while end < len(lines) and not lines[end].lstrip().startswith("#"):
                    end += 1
                while end > index + 1 and not lines[end - 1].strip():
                    end -= 1
                lines.insert(end, bullet)
                return lines

    if not any(line.strip() == FILED_HEADING for line in lines):
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(FILED_HEADING)
        lines.append("")
    lines.append(bullet)
    return lines


@blueprint.node
def file_backlog_items(
    logger: logging.Logger, spec_dir: str = "", docs_path: str = ""
) -> BacklogDrain:
    """Append this story's filed items to the repo backlog, de-duplicated, then clear them.

    The items file is removed once reconciled — every item either appended or already
    present — so a rerun cannot re-file them. It is kept only when the backlog could not be
    created at all, which is the one path where the items would otherwise be lost.
    """
    root = find_docs_root(docs_path)
    spec = spec_dir.strip()
    if not spec:
        logger.info("no spec_dir supplied — nothing to drain")
        return BacklogDrain(notes="no spec_dir supplied — nothing to drain")

    items_path = root / spec / "backlog-items.json"
    items = _load_items(logger, items_path)
    if not items:
        logger.info("no backlog items to file at %s", items_path)
        return BacklogDrain(notes="no backlog items to file")

    backlog_path = root / BACKLOG_REL
    if not backlog_path.is_file():
        try:
            backlog_path.parent.mkdir(parents=True, exist_ok=True)
            backlog_path.write_text("# Backlog\n", encoding="utf-8")
        except OSError as exc:
            logger.warning("could not create backlog at %s: %s", BACKLOG_REL, exc)
            return BacklogDrain(
                skipped=len(items),
                notes=(
                    f"no backlog at {BACKLOG_REL} and could not create it — "
                    f"{len(items)} item(s) not filed (items file kept)"
                ),
            )

    lines = backlog_path.read_text(encoding="utf-8").splitlines()
    seen = Seen(lines)

    appended = 0
    skipped = 0
    for item in items:
        item_id = kebab(item.get("id") or "")
        desc = str(item.get("description") or "").strip().replace("\n", " ")
        if not item_id or not desc or seen.duplicate(item_id, desc):
            skipped += 1
            continue
        lines = _insert_under_section(lines, str(item.get("section") or ""), f"- [{item_id}] {desc}")
        seen.add(item_id, desc)
        appended += 1

    if appended:
        backlog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    try:
        items_path.unlink()
        removed = True
    except OSError as exc:
        logger.warning("could not remove items file: %s", exc)
        removed = False

    note = f"filed {appended}, skipped {skipped} (duplicate/invalid)"
    note += "; removed backlog-items.json" if removed else "; backlog-items.json left in place"
    logger.info(note)
    return BacklogDrain(appended=appended, skipped=skipped, notes=note)


__all__ = ["BACKLOG_ID_RE", "Seen", "file_backlog_items", "id_token_set", "kebab", "norm_desc"]
