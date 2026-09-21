"""The `capture:` bullet grammar: a fact a scenario produces by running, and where to read it."""

from __future__ import annotations

from dataclasses import dataclass

from ostler.qa import references

_SEP = " from "


@dataclass(frozen=True)
class CaptureDecl:
    """One `capture:` bullet: the name a later `$name` resolves to, and where it is read."""

    name: str
    source: str


def parse_bullet(value: str) -> CaptureDecl | str:
    """Parse one `capture:` bullet, or return the sentence explaining why it is not one."""
    text = " ".join(value.split())
    if not text:
        return "empty"
    name, sep, source = text.partition(_SEP)
    name = name.strip()
    source = source.strip()
    if not sep:
        return "names no source — the grammar is `<name> from <json path | UI locator>`"
    if not name:
        return "names no capture before `from`"
    if not source:
        return "names nothing after `from` to read the value out of"
    if name.startswith("$"):
        return (
            f"`{name}` carries the `$` a reference spells — the declaration mints the name "
            f"(`{name[1:] or '<name>'}`) and later bullets refer to it as `{name}`"
        )
    if not isinstance(references.parse_reference(f"${name}"), references.CaptureRef):
        return (
            f"`{name}` is not a name a `$` reference could spell — it must start with a "
            f"letter or digit and carry only letters, digits, `_` and `-`"
        )
    return CaptureDecl(name=name, source=source)
