"""The tracked half of a fixture: what git carries when the zip cannot travel in it."""

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

    source: str = ""

    tree_sha256: str = ""

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
        """Raise unless *source* still hashes to what this pointer recorded at capture."""
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
        """Raise unless *zip_path* is byte-for-byte the archive this pointer describes."""
        if not zip_path.exists():
            raise PointerError(f"{zip_path}: missing (fetch it, or capture the seed)")
        actual = digest(zip_path)
        if actual != self.sha256:
            raise PointerError(
                f"{zip_path}: sha256 is {actual}, pointer '{self.name}' expects {self.sha256}"
            )


DIAGNOSTIC_MARKER = "DIAGNOSTIC — "


class ResultPointer(Pointer):
    """A result is a seed pointed the other way; it just knows which run made it."""

    task: str = ""
    label: str = ""
    steps: int = 0
    scored: bool = False

    caveats: list[str] = []

    @model_validator(mode="after")
    def _caveats_reach_the_note(self) -> Self:
        """Make an uncaveated note impossible to write for a compromised round."""
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
