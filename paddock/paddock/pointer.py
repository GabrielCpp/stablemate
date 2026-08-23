"""The tracked half of a fixture: what git carries when the zip cannot travel in it.

A pointer is small, textual and scannable, which is the whole reason it exists — see
`paddock.paths` for why the zip itself stays out of the tree. It says what the zip is
(name, size, sha256), what state it was captured from (`head`, `dirty`), where to get it
if it is not on this machine (`url`), and what directory name it unpacks back into
(`repo_dir`).

`repo_dir` is the field that looks cosmetic and is not: farrier derives the names of the
files it generates from the repo directory's basename, so a tree unpacked under a
different name gets a fresh set of generated skills while the ones the seed carries
dangle. The captured basename travels with the zip so unpack cannot get it wrong.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Self

import tomli_w
from pydantic import BaseModel, ConfigDict, model_validator

from paddock.archive import digest
from paddock.archive import tree_digest as digest_tree


class PointerError(RuntimeError):
    """A pointer that will not parse, or a zip that does not match one."""


class Pointer(BaseModel):
    """Outside data — hand-edited in the tree, and fetched over the network."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    repo_dir: str
    sha256: str
    bytes: int
    head: str = ""
    dirty: bool = False
    url: str = ""
    note: str = ""

    #: The captured tree's own path, relative to the data directory, when the tree lives
    #: in this repo — `apps/claims-api` for a frozen fixture. Empty for a seed captured
    #: from somewhere else on disk (a greenfield capture out of a live session), which has
    #: no in-tree source to compare against and is exempt from the freshness guard by
    #: construction rather than by exception.
    source: str = ""

    #: `archive.tree_digest` of that source directory at capture time. The pair
    #: (`source`, `tree_sha256`) is what makes an edit to a tracked fixture that never
    #: reached a re-capture a test failure instead of a round scored against the previous
    #: book — see `sha256` for the question it does *not* answer.
    tree_sha256: str = ""

    #: The `--exclude` globs the capture was taken with. `tree_sha256` was computed with
    #: them, so a verification that forgot them would hash a tree the capture never saw
    #: and report drift nobody introduced; recording them is what makes the digest
    #: reproducible from the pointer alone. Empty for a capture that excluded nothing.
    excludes: tuple[str, ...] = ()

    @classmethod
    def load(cls, path: Path) -> Self:
        try:
            raw: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise PointerError(f"{path}: {exc}") from exc
        try:
            return cls.model_validate(raw)
        except ValueError as exc:
            raise PointerError(f"{path}: {exc}") from exc

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(self.model_dump()), encoding="utf-8")
        return path

    def verify_tree(self, source: Path) -> None:
        """Raise unless *source* still hashes to what this pointer recorded at capture.

        Separate from `verify` because they catch opposite failures. `verify` asks whether
        the zip in the store is the archive this pointer names; this asks whether that
        archive is still the tree the repo tracks. The second is the one a fixture author
        trips: the trials materialize from the unpacked zip, so an edit that lands in git
        and never reaches a re-capture leaves every round scoring the previous content,
        against an answer key read from the new one.
        """
        if not self.tree_sha256:
            raise PointerError(f"pointer '{self.name}' records no tree_sha256; re-capture it")
        actual = digest_tree(source, self.excludes)
        if actual != self.tree_sha256:
            flags = "".join(f" --exclude {glob}" for glob in self.excludes)
            raise PointerError(
                f"{source}: tree has changed since seed '{self.name}' was captured "
                f"({actual[:12]} != {self.tree_sha256[:12]}). The trials materialize from the "
                f"zip, not from this tree, so the change is invisible to a round until you "
                f"re-capture:\n  uv run paddock seed capture {source} --name {self.name} --force{flags}"
            )

    def verify(self, zip_path: Path) -> None:
        """Raise unless *zip_path* is byte-for-byte the archive this pointer describes.

        Checked on every unpack, not only after a fetch. A zip in the local store was
        put there by some earlier command, possibly under a different version of the
        fixture, and a seed that has quietly drifted is a benchmark result that means
        nothing — the failure it produces is a scoring difference nobody can attribute.
        """
        if not zip_path.exists():
            raise PointerError(f"{zip_path}: missing (fetch it, or capture the seed)")
        actual = digest(zip_path)
        if actual != self.sha256:
            raise PointerError(
                f"{zip_path}: sha256 is {actual}, pointer '{self.name}' expects {self.sha256}"
            )


#: What a compromised round's note has to start with. Prose, because the note is read by
#: humans, and a fixed prefix, because it is also the thing a script greps for.
DIAGNOSTIC_MARKER = "DIAGNOSTIC — "


class ResultPointer(Pointer):
    """A result is a seed pointed the other way; it just knows which run made it."""

    task: str = ""
    label: str = ""
    steps: int = 0
    scored: bool = False

    #: Why this result is a diagnostic and not a baseline: a parked or hand-answered
    #: operator gate, a step that failed, a pin that drifted. Machine-readable on purpose.
    #: The scorecard already warns about all of this, at length — but the scorecard is
    #: printed once, to a terminal, and *this file* is what a later comparison actually
    #: reads. A caveat that lives only where a human was looking is the same defect as a
    #: decision sheet stamped without checking what was asked.
    caveats: list[str] = []

    @model_validator(mode="after")
    def _caveats_reach_the_note(self) -> Self:
        """Make an uncaveated note impossible to write for a compromised round.

        Fail-closed at the writer rather than checked at the reader, because the reader
        is a future comparison that has no way to know what it is missing: an honest
        number and a compromised one look identical once the warning is gone. Enforced in
        both directions — an unmarked note on a caveated round is the failure this exists
        to stop, and a marked note on a clean round is a marker that would stop meaning
        anything if it could be left behind by accident.
        """
        marked = self.note.startswith(DIAGNOSTIC_MARKER)
        if self.caveats and not marked:
            raise ValueError(
                f"result '{self.name}' records {len(self.caveats)} caveat(s) "
                f"({'; '.join(self.caveats)}) but its note does not say so. A caveated "
                f"round is a diagnostic: its note must begin {DIAGNOSTIC_MARKER!r}."
            )
        if marked and not self.caveats:
            raise ValueError(
                f"result '{self.name}' is marked {DIAGNOSTIC_MARKER!r} but records no "
                f"caveats. Say what compromised it, or drop the marker."
            )
        return self


def describe(pointer: Pointer) -> str:
    """One line for `paddock list` and for a command's own confirmation output."""
    head = pointer.head[:12] or "(no head)"
    dirty = " +dirty" if pointer.dirty else ""
    size = pointer.bytes / (1024 * 1024)
    return f"{pointer.name}  {head}{dirty}  {size:.1f} MiB  {pointer.repo_dir}/"


def field_names() -> tuple[str, ...]:
    return tuple(Pointer.model_fields)
