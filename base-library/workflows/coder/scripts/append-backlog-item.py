#!/usr/bin/env python3
"""Drain coder-discovered backlog items into the repo backlog (the coder→author edge).

When the coder (implement / review / QA) finds work that is **genuinely separate scope** — a
different surface, a contract mismatch in an untouched layer, a follow-on this story should not
absorb — it must neither silently drop it nor scope-creep into it. Instead it writes the item to
``<spec_dir>/backlog-items.json`` and this deterministic node appends it to the repo backlog, so
the author workflow authors it next run. A coder-filed ``[id]`` is also a valid owner for a
``deferred`` gap, so the author's coverage gate resolves it — the loop closes.

Guardrail lives in the prompts, not here: only *separate* scope is filed; a buildable in-scope
precondition is BUILT by the implementer, never punted to the backlog.

This filer is intentionally conservative:
  - enforces the backlog format contract: one ``- [kebab-id] <one self-contained line>`` bullet,
    no nested bullets, id matched/sanitized to a stable kebab handle.
  - **de-duplicates** against the backlog (and within the batch) so reruns and repeated QA
    passes never pile up duplicates. Three HIGH-PRECISION signals, any of which skips the item:
      (1) same ``[id]`` (the original guard);
      (2) same normalized description text (a copy-paste re-file under a fresh id);
      (3) same *set* of id tokens (a word-permuted re-file, e.g.
          ``projects-new-cold-navigation-loses-route-match`` vs
          ``cold-navigation-projects-new-loses-route-match``).
    These are deliberately exact-match, not fuzzy: two items that merely *share some words*
    (e.g. two distinct translation-table gaps that both mention "choice fields") are NOT
    merged — dropping genuinely-separate scope is worse than filing a near-duplicate, since the
    author's coverage gate depends on filed items.
  - appends under the item's named ``## section`` heading when it exists; otherwise under a
    "## Filed by coder" heading appended at end (created once).
  - **creates** the backlog (a minimal ``# Backlog`` scaffold) when it does not exist yet, so the
    very first filed item — or a coder-only repo with no author backlog — still captures the work
    instead of dropping it.
  - **removes** ``<spec_dir>/backlog-items.json`` once it has been reconciled into the backlog
    (items either appended or already present) so the same items are never re-filed and no stale
    artifact lingers in the spec dir. The file is kept only when the backlog could not be created
    (a read-only / unwritable target), so those items aren't lost.
  - best-effort: a missing items file or a malformed entry degrades to a logged no-op, and an
    unwritable backlog degrades to keeping the items file — it never aborts the coder run
    (mirrors prune-backlog / check_feedback).

Input ``<spec_dir>/backlog-items.json`` — a JSON array (or {"items": [...]}); each item:
  {"id": "section-tree-rebuild", "description": "BUG: …", "section": "## Projects"}  (section optional)

Usage: append-backlog-item.py <spec_dir> [docs_path]
Outputs JSON: {"backlog_items_appended": <n>, "backlog_items_skipped": <n>, "notes": "..."}
"""
from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root

BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")
_FILED_HEADING = "## Filed by coder"
# A trailing ``(blocked: ...)`` annotation (added by mark-fix-blocked.py) is not part of the
# item's identity — strip it before comparing descriptions so a re-file of a blocked item's
# text still de-dups against it.
_BLOCKED_SUFFIX_RE = re.compile(r"\s*\(blocked\b.*$", re.IGNORECASE)


def kebab(raw: str) -> str:
    """Sanitize an id to a stable kebab handle (matches the backlog [id] grammar)."""
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw).strip().lower()).strip("-")
    return s


def norm_desc(desc: str) -> str:
    """Normalize a description to an identity key: strip a trailing ``(blocked...)`` marker,
    lowercase, drop punctuation, collapse whitespace. Empty string → no key (never matches)."""
    d = _BLOCKED_SUFFIX_RE.sub("", str(desc or ""))
    d = re.sub(r"[^a-z0-9]+", " ", d.lower()).strip()
    return d


def id_token_set(iid: str) -> frozenset[str]:
    """The set of tokens in a kebab id — order-insensitive, so a word-permuted re-file of the
    same handle collides. Empty → empty set (never matches, guarded by the caller)."""
    return frozenset(t for t in re.split(r"[.\-_]+", str(iid or "").lower()) if t)


class Seen:
    """The three high-precision de-dup signals, seeded from the backlog and grown per batch."""

    def __init__(self, lines: list[str]) -> None:
        self.ids: set[str] = set()
        self.descs: set[str] = set()
        self.idsets: set[frozenset[str]] = set()
        for line in lines:
            m = BACKLOG_ID_RE.match(line)
            if not m:
                continue
            self.add(m.group(1), m.group(2))

    def add(self, iid: str, desc: str) -> None:
        if iid:
            self.ids.add(iid)
            toks = id_token_set(iid)
            if toks:
                self.idsets.add(toks)
        key = norm_desc(desc)
        if key:
            self.descs.add(key)

    def duplicate(self, iid: str, desc: str) -> bool:
        if iid and iid in self.ids:
            return True
        toks = id_token_set(iid)
        if toks and toks in self.idsets:
            return True
        key = norm_desc(desc)
        return bool(key and key in self.descs)


def emit(appended: int, skipped: int, notes: str) -> None:
    print(json.dumps({
        "backlog_items_appended": appended,
        "backlog_items_skipped": skipped,
        "notes": notes,
    }))


def load_items(items_path: Path) -> list[dict]:
    if not items_path.is_file():
        return []
    try:
        data = json.loads(items_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"[append-backlog-item] items file unreadable: {e}", file=sys.stderr)
        return []
    if isinstance(data, dict):
        data = data.get("items") or []
    return [it for it in data if isinstance(it, dict)]


def insert_under_section(lines: list[str], section: str, bullet: str) -> list[str]:
    """Insert ``bullet`` at the end of the named ``## section`` block; if the section is not
    found, append it under a single "## Filed by coder" heading at end of file."""
    if section:
        target = section.strip().lstrip("#").strip().lower()
        for i, line in enumerate(lines):
            if line.lstrip().startswith("#") and line.lstrip("#").strip().lower() == target:
                # find end of this section (next heading or EOF), back up over trailing blanks
                j = i + 1
                while j < len(lines) and not lines[j].lstrip().startswith("#"):
                    j += 1
                k = j
                while k > i + 1 and not lines[k - 1].strip():
                    k -= 1
                lines.insert(k, bullet)
                return lines

    # Fallback: append under a single "Filed by coder" heading.
    if not any(line.strip() == _FILED_HEADING for line in lines):
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(_FILED_HEADING)
        lines.append("")
    lines.append(bullet)
    return lines


def main(logger: logging.Logger) -> None:
    spec_dir = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    docs_path_arg = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    root = find_docs_root(docs_path_arg)
    backlog_rel = "docs/backlog.md"

    if not spec_dir:
        logger.info("no spec_dir supplied — nothing to drain")
        emit(0, 0, "no spec_dir supplied — nothing to drain")
        return

    items_path = root / spec_dir / "backlog-items.json"
    items = load_items(items_path)
    if not items:
        logger.info("no backlog items to file at %s", items_path)
        emit(0, 0, "no backlog items to file")
        return

    backlog_path = root / backlog_rel
    if not backlog_path.is_file():
        # No backlog yet (e.g. a coder-only repo, or the very first item ever filed) — create a
        # minimal one so the items are captured here rather than dropped. The items then drain
        # under a "## Filed by coder" heading like any other coder-filed scope.
        try:
            backlog_path.parent.mkdir(parents=True, exist_ok=True)
            backlog_path.write_text("# Backlog\n", encoding="utf-8")
        except OSError as e:
            # Truly unwritable (read-only fs / bad path) — degrade to a no-op, keep the items
            # file so a later run can still drain them.
            logger.warning("could not create backlog at %s: %s", backlog_rel, e)
            emit(0, len(items), f"no backlog at {backlog_rel} and could not create it — {len(items)} item(s) not filed (items file kept)")
            return

    text = backlog_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    seen = Seen(lines)  # de-dup against the backlog AND earlier items this batch

    appended = 0
    skipped = 0
    for it in items:
        iid = kebab(it.get("id") or "")
        desc = str(it.get("description") or "").strip().replace("\n", " ")
        if not iid or not desc:
            skipped += 1
            continue
        if seen.duplicate(iid, desc):  # same id, same text, or same id-token-set
            skipped += 1
            continue
        bullet = f"- [{iid}] {desc}"
        lines = insert_under_section(lines, str(it.get("section") or ""), bullet)
        seen.add(iid, desc)
        appended += 1

    if appended:
        backlog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # The items file has been fully reconciled into an existing backlog (every item was either
    # appended or already present / invalid) — remove it so reruns don't re-scan it and no stale
    # artifact lingers in the spec dir. Best-effort: a failed unlink never aborts the run.
    removed = False
    try:
        items_path.unlink()
        removed = True
    except OSError as e:
        logger.warning("could not remove items file: %s", e)

    note = f"filed {appended}, skipped {skipped} (duplicate/invalid)"
    note += "; removed backlog-items.json" if removed else "; backlog-items.json left in place"
    logger.info(note)
    emit(appended, skipped, note)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("append-backlog-item"))
