"""The Import — turning an old ``- [id] text`` bullet list into records on the shelf, once."""

from __future__ import annotations

import re
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path

import pydantic

from ostler import ids, markdown, register
from ostler.model import Graph

PATTERN = "untriaged"
GENERAL = "general"
SUMMARY_LIMIT = 160

_TOP_BULLET = re.compile(r"\s{0,3}[-*+]\s")
_MARKER = re.compile(r"^\s*[-*+]\s+(?:\[[^\]\n]*\](?!\()\s*)?")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s")
_KNOWN_TITLES: dict[str, tuple[register.FiledBy, str]] = {
    "filed by coder": ("qa", "untriaged"),
    "deferred by coder": ("coder", "untriaged"),
    "book checks qa could not run": ("qa-deferred", "book"),
    "survey findings": ("survey", "untriaged"),
    "legacy surfaces missing from the new app": ("parity", "untriaged"),
}


@dataclass(frozen=True, slots=True)
class Imported:
    """The outcome of one import: the records it built, how many kept their id, and why it stopped when it did."""

    ok: bool
    message: str
    records: tuple[register.Record, ...] = ()
    kept: int = 0


def _kebab(text: str) -> str:
    """A heading as an area segment: cut at the first ' | ', lowercase, ``[a-z0-9-]``, edge dashes stripped."""
    cut = text.split(" | ", 1)[0].lower()
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", cut)).strip("-")


def _summary(text: str) -> str:
    """The first sentence of *text* on one line, cut at a word boundary within the limit, with ``…`` when cut."""
    flat = " ".join(text.split())
    sentence = _SENTENCE_END.split(flat, maxsplit=1)[0]
    if len(sentence) <= SUMMARY_LIMIT:
        return sentence
    cut = sentence[: SUMMARY_LIMIT + 1]
    head = cut.rsplit(" ", 1)[0] if " " in cut[1:] else cut[:SUMMARY_LIMIT]
    return head[:SUMMARY_LIMIT].rstrip() + "…"


def _body_of(lines: list[str]) -> str:
    """A bullet's lines as written, less its marker and id, with the continuation lines dedented."""
    first = _MARKER.sub("", lines[0], count=1)
    rest = textwrap.dedent("\n".join(lines[1:])).strip("\n")
    return f"{first}\n{rest}".rstrip() if rest else first.rstrip()


def _own_id(bullet: markdown.Bullet) -> str:
    """The id a bullet carries in its ``[id]`` marker, or empty when it has none or the bracket is not an id."""
    ident, _ = bullet.bracketed
    return ident if ident and register.ID_PATTERN.fullmatch(ident) else ""


def _context(section: markdown.Section, first: int, titled: bool) -> str:
    """The ``## Context`` of every record of one section: the heading it sat under and the prose before its first bullet."""
    start = section.line_start + (1 if section.level else 0)
    prose = "\n".join(section.body_lines[start:first]).strip()
    head = (
        f'Filed under the heading "{section.title.strip()}".' if titled else "Filed under no heading."
    )
    return f"## Context\n\n{head}" + (f"\n\n{prose}" if prose else "")


def _title_line(doc: markdown.MarkdownDoc) -> int:
    """The line of a document title: a level-1 heading on the first non-blank line, or -1."""
    lines = doc.body.split("\n")
    first = next((i for i, line in enumerate(lines) if line.strip()), -1)
    top = next((s for s in doc.walk_sections() if s.level), None)
    return first if top is not None and top.level == 1 and top.line_start == first else -1


def _built(
    graph: Graph, text: str, repo: str, prefix: str | None
) -> tuple[list[register.Record], set[str], str]:
    """Every record the list yields, the ids it kept, and the reason it cannot be built when it cannot."""
    doc = markdown.split(text)
    lines = doc.body.split("\n")
    title = _title_line(doc)
    built: list[register.Record] = []
    kept: set[str] = set()
    for section in doc.walk_sections():
        tops = [b for b in section.bullets if _TOP_BULLET.match(lines[b.line_start])]
        if not tops:
            continue
        titled = bool(section.level) and section.line_start != title
        known = _KNOWN_TITLES.get(section.title.strip().lower()) if titled else None
        filed_by, area = known or ("person", (_kebab(section.title) if titled else "") or GENERAL)
        context = _context(section, tops[0].line_start, titled)
        for bullet in tops:
            ident = _own_id(bullet)
            wrapped = lines[bullet.line_start:bullet.line_end]
            while wrapped and not wrapped[-1].strip():
                wrapped.pop()
            try:
                record = register.Record(
                    id=ident or ids.allocate(graph, prefix), repo=repo, area=area, pattern=PATTERN,
                    filed_by=filed_by, summary=_summary(bullet.bracketed[1] if ident else bullet.text),
                    body=f"{_body_of(wrapped)}\n\n{context}",
                )
            except pydantic.ValidationError as exc:
                first = exc.errors()[0]
                where = f"line {bullet.line_start + doc.body_offset + 1}"
                return [], kept, f"invalid record at {where}: {'.'.join(map(str, first['loc']))}: {first['msg']}"
            if ident:
                kept.add(ident)
            built.append(record)
    return built, kept, ""


def _rollback(written: list[Path]) -> None:
    """Take every record this import wrote off the shelf."""
    for file in written:
        register.discard(file)


def import_list(graph: Graph, source: Path, repo: str, prefix: str | None = None) -> Imported:
    """Turn the bullets of *source* into records of *repo*, all or none, commit them in the artifacts repo, then delete *source*."""
    if not source.is_file():
        return Imported(False, f"no list at {source}")
    built, kept, reason = _built(graph, source.read_text(encoding="utf-8"), repo, prefix)
    if reason:
        return Imported(False, reason)
    if not built:
        return Imported(False, f"no bullets to import in {source}")
    every = [r.id for r in built]
    twice = sorted({i for i in every if every.count(i) > 1})
    if twice:
        return Imported(False, f"ids used twice in {source}: {', '.join(twice)}")
    taken = sorted(kept & ids.claimed(graph))
    if taken:
        return Imported(False, f"ids already taken in the workspace: {', '.join(taken)}")
    written: list[Path] = []
    for record in built:
        result = register.write(graph, record, own=frozenset(kept))
        if not result.ok:
            _rollback(written)
            return Imported(False, result.message)
        written.extend(result.paths)
    try:
        register.commit(graph, written, f"chore({repo}): import the backlog list")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        _rollback(written)
        return Imported(False, f"nothing imported: the artifacts commit failed: {exc}")
    source.unlink()
    return Imported(True, f"imported {len(built)} records, kept {len(kept)} ids", tuple(built), len(kept))
