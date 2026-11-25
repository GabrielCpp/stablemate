"""Round-trip YAML helpers that keep comments, key order and quoting through a merge."""

from __future__ import annotations

from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import ScalarString


def round_trip_yaml(source: str = "") -> YAML:
    """Round-trip loader/dumper: comments, key order and flow style survive the merge."""
    y = YAML()
    y.preserve_quotes = True
    y.default_flow_style = False
    y.width = 4096
    seq = sequence_indent(source)
    y.indent(mapping=2, sequence=seq + 2, offset=seq)
    return y


def sequence_indent(source: str, default: int = 2) -> int:
    """How far `source` indents a top-level block-sequence item, or `default`."""
    indents = [
        len(line) - len(line.lstrip(" "))
        for line in source.splitlines()
        if line.lstrip(" ").startswith("- ") or line.strip() == "-"
    ]
    return min(indents) if indents else default


def assign_seq(mapping: dict, key: str, merged: list) -> None:
    """Set `mapping[key]` to `merged`, keeping the existing sequence node when possible."""
    current = mapping.get(key)
    if isinstance(current, list) and list(current) == merged[: len(current)]:
        current.extend(
            like(current[0] if current else None, item)
            for item in merged[len(current) :]
        )
        return
    mapping[key] = merged


def like(sibling, value: str):
    """Return `value` quoted the way `sibling` is quoted."""
    return type(sibling)(value) if isinstance(sibling, ScalarString) else value
