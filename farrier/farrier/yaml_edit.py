"""Line-level edits of `agents.yml` that keep every other byte and comment as written."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml

from farrier.naming import yaml_quote

_ITEM = re.compile(r"^(?P<indent> *)-(?P<gap> +)(?P<value>\S.*)$")
_KEY = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][\w-]*)[ \t]*:(?P<rest>.*)$")


class Document:
    """The lines of one YAML file, edited in place and joined back with their own line endings."""

    def __init__(self, text: str):
        self.crlf = "\r\n" in text
        self.lines = text.split("\n")

    def text(self) -> str:
        return "\n".join(self.lines)

    def new(self, content: str) -> str:
        """*content* as a line of this document, with its line ending."""
        return content + ("\r" if self.crlf else "")

    def bare(self, index: int) -> str:
        return self.lines[index].rstrip("\r")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _skippable(line: str) -> bool:
    stripped = line.strip()
    return not stripped or stripped.startswith("#")


def _is_dash(line: str) -> bool:
    stripped = line.lstrip(" ")
    return stripped == "-" or stripped.startswith("- ")


def scalar(value: str) -> str:
    """*value* as a YAML scalar that reads back as the same string."""
    if re.fullmatch(r"[\w./-]+", value) and yaml.safe_load(value) == value:
        return value
    return yaml_quote(value)


def top_level_key(doc: Document, key: str, start: int = 0) -> int | None:
    """The index of the column-0 line `key:` at or after *start*, or None."""
    for index in range(start, len(doc.lines)):
        match = _KEY.match(doc.bare(index))
        if match and not match["indent"] and match["key"] == key:
            return index
    return None


def block_end(doc: Document, at: int, indent: int) -> int:
    """One past the last content line of the block the key at line *at* (indented *indent*) opens."""
    last = at
    for index in range(at + 1, len(doc.lines)):
        line = doc.bare(index)
        if _skippable(line):
            continue
        depth = _indent(line)
        if depth > indent or (depth == indent and _is_dash(line)):
            last = index
        else:
            break
    return last + 1


def _inline(rest: str) -> str:
    """What follows a key's colon on its line, without a trailing comment."""
    return re.sub(r"\s+#.*$", "", rest).strip()


def _entry_value(text: str) -> str:
    """The string a list item's text denotes, or an empty string when it is not one."""
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError:
        return ""
    return value if isinstance(value, str) else ""


def rewrite_skills_list(text: str, rewrites: Mapping[str, Sequence[str]]) -> str:
    """Replace each top-level `skills:` entry named in *rewrites* by the ids it maps to."""
    doc = Document(text)
    at = top_level_key(doc, "skills")
    if at is None:
        raise SystemExit("agents.yml has no top-level `skills:` list to edit")
    match = _KEY.match(doc.bare(at))
    assert match is not None
    if _inline(match["rest"]):
        raise SystemExit(
            "agents.yml writes `skills:` in flow style, and eject edits block lists "
            "only. Rewrite it as one `- id` line per entry, then eject again."
        )
    end = block_end(doc, at, 0)
    rebuilt: list[str] = []
    for index in range(at + 1, end):
        line = doc.bare(index)
        item = _ITEM.match(line)
        if item is not None and _entry_value(item["value"]) in rewrites:
            rebuilt.extend(
                doc.new(f"{item['indent']}-{item['gap']}{scalar(new)}")
                for new in rewrites[_entry_value(item["value"])]
            )
            continue
        rebuilt.append(doc.lines[index])
    if any(_ITEM.match(line.rstrip("\r")) for line in rebuilt):
        doc.lines[at + 1 : end] = rebuilt
    else:
        doc.lines[at : end] = rebuilt
    return doc.text()


def add_excluded_skill(text: str, skill_id: str) -> str:
    """Add *skill_id* to `exclude.skills`, creating the keys when they are missing."""
    doc = Document(text)
    entry = scalar(skill_id)
    exclude = top_level_key(doc, "exclude")
    if exclude is None:
        if doc.lines and doc.lines[-1] == "":
            doc.lines.pop()
        doc.lines += [
            doc.new("exclude:"),
            doc.new("  skills:"),
            doc.new(f"    - {entry}"),
            "",
        ]
        return doc.text()
    match = _KEY.match(doc.bare(exclude))
    assert match is not None
    inline = _inline(match["rest"])
    if inline == "{}":
        doc.lines[exclude] = doc.new("exclude:")
    elif inline:
        raise SystemExit(
            "agents.yml writes `exclude:` in flow style, and eject edits block "
            "mappings only. Rewrite it in block style, then eject again."
        )
    end = block_end(doc, exclude, 0)
    child_indent = next(
        (
            _indent(doc.bare(i))
            for i in range(exclude + 1, end)
            if not _skippable(doc.bare(i))
        ),
        2,
    )
    skills = None
    for index in range(exclude + 1, end):
        child = _KEY.match(doc.bare(index))
        if child and len(child["indent"]) == child_indent and child["key"] == "skills":
            skills = index
            break
    if skills is None:
        doc.lines[end:end] = [
            doc.new(f"{' ' * child_indent}skills:"),
            doc.new(f"{' ' * (child_indent + 2)}- {entry}"),
        ]
        return doc.text()
    child = _KEY.match(doc.bare(skills))
    assert child is not None
    inline = _inline(child["rest"])
    if inline == "[]":
        doc.lines[skills] = doc.new(f"{' ' * child_indent}skills:")
    elif inline:
        raise SystemExit(
            "agents.yml writes `exclude.skills` in flow style, and eject edits block "
            "lists only. Rewrite it as one `- id` line per entry, then eject again."
        )
    skills_end = block_end(doc, skills, child_indent)
    items = [
        _ITEM.match(doc.bare(i))
        for i in range(skills + 1, skills_end)
        if _ITEM.match(doc.bare(i))
    ]
    indent = items[0]["indent"] if items and items[0] else " " * (child_indent + 2)
    doc.lines.insert(skills_end, doc.new(f"{indent}- {entry}"))
    return doc.text()


@dataclass
class Chunk:
    """One key of a localInstructions entry with its lines, or a run of comments between keys."""

    key: str | None
    lines: list[str] = field(default_factory=list)


def _split_entry(doc: Document, start: int, end: int) -> tuple[str, int, list[Chunk]]:
    """``(dash prefix, key indent, chunks)`` for the entry spanning lines ``start:end``."""
    first = _ITEM.match(doc.bare(start))
    if first is None:
        raise SystemExit(
            "agents.yml writes a localInstructions entry whose first key is not on "
            "its dash line. Move the first key up beside the `-`, then eject again."
        )
    key_indent = len(first["indent"]) + 1 + len(first["gap"])
    prefix = f"{first['indent']}-{first['gap']}"
    lines = [doc.lines[start][len(prefix) :]]
    lines[0] = " " * key_indent + lines[0]
    lines += doc.lines[start + 1 : end]
    chunks: list[Chunk] = []
    for line in lines:
        bare = line.rstrip("\r")
        match = _KEY.match(bare)
        if match and len(match["indent"]) == key_indent:
            chunks.append(Chunk(match["key"], [line]))
        elif chunks:
            chunks[-1].lines.append(line)
        else:
            raise SystemExit(
                "agents.yml has a localInstructions entry eject cannot read"
            )
    out: list[Chunk] = []
    for chunk in chunks:
        tail: list[str] = []
        while len(chunk.lines) > 1 and _filler(chunk.lines[-1], key_indent):
            tail.insert(0, chunk.lines.pop())
        out.append(chunk)
        if tail:
            out.append(Chunk(None, tail))
    return prefix, key_indent, out


def _filler(line: str, key_indent: int) -> bool:
    bare = line.rstrip("\r")
    if not bare.strip():
        return True
    return _indent(bare) <= key_indent and bare.strip().startswith("#")


def _chunk_value(chunk: Chunk, key_indent: int) -> Any:
    """The parsed value of one key chunk."""
    dedented = "\n".join(line.rstrip("\r")[key_indent:] for line in chunk.lines)
    parsed = yaml.safe_load(dedented)
    return parsed[chunk.key] if isinstance(parsed, dict) else None


def block_scalar(doc: Document, key: str, key_indent: int, value: str) -> list[str]:
    """The lines of `key: |` holding *value*, which ends in exactly one newline."""
    body = value.rstrip("\n").split("\n")
    indicator = "2" if body[0][:1] in (" ", "\t") else ""
    lines = [doc.new(f"{' ' * key_indent}{key}: |{indicator}")]
    lines += [
        doc.new(f"{' ' * (key_indent + 2)}{line}" if line else "") for line in body
    ]
    return lines


def _drop_names(
    doc: Document, chunk: Chunk, key_indent: int, drop: Callable[[str], bool]
) -> list[str] | None:
    """The chunk's lines after dropping matching names, or None to remove the chunk."""
    value = _chunk_value(chunk, key_indent)
    names = value if isinstance(value, list) else [value]
    kept = [str(name) for name in names if not drop(str(name))]
    if len(kept) == len(names):
        return chunk.lines
    if not kept:
        return None
    head = chunk.lines[0].rstrip("\r")
    if "[" in head:
        names_text = ", ".join(scalar(name) for name in kept)
        return [doc.new(f"{' ' * key_indent}{chunk.key}: [{names_text}]")]
    out = [chunk.lines[0]]
    for line in chunk.lines[1:]:
        item = _ITEM.match(line.rstrip("\r"))
        if item and drop(_entry_value(item["value"])):
            continue
        out.append(line)
    return out


def rewrite_local_instruction(
    text: str,
    index: int,
    drop_policy: Callable[[str], bool],
    new_text: str | None,
) -> str:
    """Drop policy names from the *index*-th localInstructions entry and set its `text:` value."""
    doc = Document(text)
    at = top_level_key(doc, "localInstructions")
    if at is None:
        raise SystemExit(
            "agents.yml has no top-level `localInstructions:` list to edit"
        )
    match = _KEY.match(doc.bare(at))
    assert match is not None
    if _inline(match["rest"]):
        raise SystemExit(
            "agents.yml writes `localInstructions:` in flow style, and eject edits "
            "block lists only."
        )
    end = block_end(doc, at, 0)
    dashes = [i for i in range(at + 1, end) if _is_dash(doc.bare(i))]
    item_indent = min(_indent(doc.bare(i)) for i in dashes)
    starts = [i for i in dashes if _indent(doc.bare(i)) == item_indent]
    start = starts[index]
    stop = starts[index + 1] if index + 1 < len(starts) else end
    prefix, key_indent, chunks = _split_entry(doc, start, stop)
    rebuilt: list[Chunk] = []
    text_done = new_text is None
    for chunk in chunks:
        if chunk.key in ("policy", "policies"):
            lines = _drop_names(doc, chunk, key_indent, drop_policy)
            if lines is not None:
                rebuilt.append(Chunk(chunk.key, lines))
        elif chunk.key == "text" and new_text is not None:
            rebuilt.append(
                Chunk("text", block_scalar(doc, "text", key_indent, new_text))
            )
            text_done = True
        else:
            rebuilt.append(chunk)
    if not text_done and new_text is not None:
        last = max(i for i, chunk in enumerate(rebuilt) if chunk.key is not None)
        rebuilt.insert(
            last + 1, Chunk("text", block_scalar(doc, "text", key_indent, new_text))
        )
    lines = [line for chunk in rebuilt for line in chunk.lines]
    first = next(i for i, chunk in enumerate(rebuilt) if chunk.key is not None)
    offset = sum(len(chunk.lines) for chunk in rebuilt[:first])
    lines[offset] = prefix + lines[offset][key_indent:]
    doc.lines[start:stop] = lines
    return doc.text()


def entry_count(text: str) -> int:
    """The number of localInstructions entries written in *text*."""
    doc = Document(text)
    at = top_level_key(doc, "localInstructions")
    if at is None:
        return 0
    end = block_end(doc, at, 0)
    dashes = [i for i in range(at + 1, end) if _is_dash(doc.bare(i))]
    if not dashes:
        return 0
    item_indent = min(_indent(doc.bare(i)) for i in dashes)
    return sum(1 for i in dashes if _indent(doc.bare(i)) == item_indent)
