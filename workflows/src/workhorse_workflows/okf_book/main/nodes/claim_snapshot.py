"""Each claim's expected outcome as the book stated it when a gate opened, and the changes to them an answer made."""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ostler import registry
from ostler.model import UINode, load
from pydantic import BaseModel, ConfigDict, TypeAdapter

from workhorse_workflows.okf_book.shared.entries import FEATURES_DIR
from workhorse_workflows.okf_book.shared.page_check import PageProblem

SNAPSHOT_FILE = "claims.json"
SETUP_TYPES = frozenset({"fixture", "runbook", "environment", "step"})


class Claim(BaseModel):
    """One normative bullet of a node: the page it sits on, the node, its key, which bullet of that key it is, and the outcome it states."""

    model_config = ConfigDict(frozen=True)

    page: str
    node: str
    key: str
    occurrence: int
    expected: str

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self.node, self.key, self.occurrence)


_CLAIMS = TypeAdapter(tuple[Claim, ...])


def _node_claims(page: str, node: UINode) -> list[Claim]:
    keys = registry.normative_keys(node.type)
    name = f"{page}#{node.anchor}" if node.anchor else page
    seen: dict[str, int] = {}
    claims: list[Claim] = []
    for key, text, _ in node.bullet_order:
        if key not in keys:
            continue
        seen[key] = seen.get(key, 0) + 1
        claims.append(Claim(page=page, node=name, key=key, occurrence=seen[key], expected=text))
    return claims


def book_claims(root: Path, services: Iterable[str]) -> tuple[Claim, ...]:
    """Every claim the books of *services* state, leaving out fixture, precondition and setup pages, whose edits are free."""
    folders = tuple(f"{(FEATURES_DIR / service).as_posix()}/" for service in services)
    resolved = root.resolve()
    claims: list[Claim] = []
    for node in load(root).ui_nodes:
        path = node.path.resolve()
        if node.type in SETUP_TYPES or not path.is_relative_to(resolved):
            continue
        page = path.relative_to(resolved).as_posix()
        if page.startswith(folders):
            claims.extend(_node_claims(page, node))
    return tuple(claims)


def write_snapshot(folder: Path, claims: tuple[Claim, ...]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    _ = (folder / SNAPSHOT_FILE).write_bytes(_CLAIMS.dump_json(claims))


def read_snapshot(folder: Path) -> tuple[Claim, ...] | None:
    path = folder / SNAPSHOT_FILE
    return _CLAIMS.validate_json(path.read_bytes()) if path.is_file() else None


def changed_claims(before: Iterable[Claim], after: Iterable[Claim]) -> tuple[PageProblem, ...]:
    """Each claim *before* stated that *after* states otherwise or no longer states, as a finding for its page's writer. A claim *after* adds is free."""
    now = {claim.identity: claim for claim in after}
    problems: list[PageProblem] = []
    for claim in before:
        stated = now.get(claim.identity)
        if stated is not None and stated.expected == claim.expected:
            continue
        change = f"to `{stated.expected}`" if stated is not None else "by removing it"
        problems.append(PageProblem(claim.page, (
            f"since the gate opened, an answer changed the `{claim.key}` claim of {claim.node} from `{claim.expected}` {change}. "
            + "A claim's expected outcome changes only through its page's writer: restore it, "
            + "unless the source shows the new outcome, and then keep it and cite that source"
        ), node=claim.node))
    return tuple(problems)
