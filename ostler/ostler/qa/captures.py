"""The `capture:` bullet grammar: a fact a scenario produces by running, and where to read it.

A `capture:` names something no book can state statically — the id the app minted for the
widget this scenario just created — and binds it to a name later bullets reference as
`$name`. Two halves, and the second is why this is a module rather than three lines inside
the packet builder: the *name* a declaration mints and the *name* a reference spells are the
same name, so they have to be the same grammar. `references` owns the reference spelling;
this validates a declaration against it rather than carrying a second copy that drifts.

The refusal is a value, not a raised error and not a silent skip. A bullet the parser could
not read used to be dropped here, which made it byte-identical downstream to a node that
declared no capture at all — and the consequence lands on a *different* bullet, the later one
whose `$name` then resolves against nothing. `parse_bullet` returns the sentence saying why,
so whoever reads the bullet next can say so about the bullet that is actually wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from ostler.qa import references

#: The em dash is deliberately not a separator here. A `fixture:` bullet carries prose after
#: one because the arrangement has a state to describe in words; a capture has a source to
#: read, and prose in that position would be a path nothing could follow.
_SEP = " from "


@dataclass(frozen=True)
class CaptureDecl:
    """One `capture:` bullet: the name a later `$name` resolves to, and where it is read."""

    name: str
    source: str


def parse_bullet(value: str) -> CaptureDecl | str:
    """Parse one `capture:` bullet, or return the sentence explaining why it is not one.

    The grammar is `<name> from <json path | UI locator>`. The name is held to the spelling
    `references` already accepts after a `$`, because a name it would not accept is a fact
    nothing in the book can ever refer to — a declaration that reads as fine and resolves for
    nobody. A leading `$` is refused by name rather than quietly stripped: the declaration
    mints the fact and the reference spells it, and admitting both spellings on the declaring
    side is how one concept comes to have two.
    """
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
