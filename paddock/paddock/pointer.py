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
from pydantic import BaseModel, ConfigDict

from paddock.archive import digest


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


class ResultPointer(Pointer):
    """A result is a seed pointed the other way; it just knows which run made it."""

    task: str = ""
    label: str = ""
    steps: int = 0
    scored: bool = False


def describe(pointer: Pointer) -> str:
    """One line for `paddock list` and for a command's own confirmation output."""
    head = pointer.head[:12] or "(no head)"
    dirty = " +dirty" if pointer.dirty else ""
    size = pointer.bytes / (1024 * 1024)
    return f"{pointer.name}  {head}{dirty}  {size:.1f} MiB  {pointer.repo_dir}/"


def field_names() -> tuple[str, ...]:
    return tuple(Pointer.model_fields)
