"""The files that build and start the stack, which no import reaches and the book still has to describe."""
from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from workhorse_workflows.okf_book.shared.citations import book_pages

_COMPOSE = frozenset({"compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"})
_MAKEFILE = "Makefile"
_RUNBOOK = re.compile(r"^type:\s*runbook\s*$", re.MULTILINE)
_MAKE_CALL = re.compile(r"\bmake\s+(?P<target>[A-Za-z0-9][\w.-]*)")
_MAKE_RULE = r"^{target}\s*:(?!=)"


def _is_build_file(path: Path) -> bool:
    name = path.name
    return name in _COMPOSE or name == "Dockerfile" or name.startswith("Dockerfile.") or name.endswith(".Dockerfile")


def ancestor_folders(root: Path, files: Iterable[str]) -> tuple[Path, ...]:
    """Every directory from each file's own up to `root`, once each, shallowest last."""
    folders: set[Path] = set()
    for rel in files:
        folder = (root / rel).parent
        while folder.is_relative_to(root) and folder not in folders:
            folders.add(folder)
            if folder == root:
                break
            folder = folder.parent
    return tuple(sorted(folders, key=lambda f: (-len(f.parts), f.as_posix())))


def _made_targets(root: Path, service: str) -> frozenset[str]:
    """The make targets a runbook page of the service tells the operator to run."""
    targets: set[str] = set()
    for page in book_pages(root, service):
        text = page.read_text(encoding="utf-8")
        if _RUNBOOK.search(text):
            targets.update(m.group("target") for m in _MAKE_CALL.finditer(text))
    return frozenset(targets)


def _defines_any(makefile: Path, targets: frozenset[str]) -> bool:
    text = makefile.read_text(encoding="utf-8", errors="replace")
    return any(re.search(_MAKE_RULE.format(target=re.escape(t)), text, re.MULTILINE) for t in targets)


def stack_files(root: Path, service: str, files: Iterable[str]) -> frozenset[str]:
    """The compose files and Dockerfiles beside `files` or above them, and a Makefile a runbook calls into."""
    targets = _made_targets(root, service)
    found: set[str] = set()
    for folder in ancestor_folders(root, files):
        for path in folder.iterdir():
            if not path.is_file():
                continue
            if _is_build_file(path) or (path.name == _MAKEFILE and targets and _defines_any(path, targets)):
                found.add(path.relative_to(root).as_posix())
    return frozenset(found)
