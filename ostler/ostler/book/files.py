"""The files a book needs to load: its own folder, and what its modules import from elsewhere under the book root.

The walk reads the modules' imports with `ast` and loads nothing. An import that does not resolve to a file under the
book root (`ostler`, the standard library, an installed package) is not listed, and neither is another service's book,
which is its own commit."""

from __future__ import annotations

import argparse
import ast
import os
import sys
from pathlib import Path

COMPILED = (".pyc", ".pyo")
CACHE = "__pycache__"


def _own(root: Path, module: str) -> Path | None:
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "services":
        return None
    folder = root / "services" / parts[1]
    return folder if folder.is_dir() else None


def _is_book(folder: Path) -> bool:
    if (folder / "service.py").is_file():
        return True
    return any((child / "service.py").is_file() for child in folder.iterdir() if child.is_dir())


def _belongs(root: Path, own: Path, path: Path) -> bool:
    if path.is_relative_to(own):
        return True
    relative = path.relative_to(root).parts
    if len(relative) < 3 or relative[0] != "services":
        return True
    return not _is_book(root / relative[0] / relative[1])


def _own_files(root: Path, own: Path) -> list[Path]:
    found: list[Path] = []
    for here, names, files in os.walk(own):
        names[:] = [name for name in names if name != CACHE]
        found += [Path(here) / name for name in files if not name.endswith(COMPILED)]
    return sorted(found)


def _dotted(root: Path, file: Path, node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    base = node.module.split(".") if node.module else []
    if node.level:
        package = list(file.relative_to(root).parts[:-1])
        keep = len(package) - (node.level - 1)
        if keep < 0:
            return []
        base = package[:keep] + base
    named = [".".join(base)] if base else []
    return named + [".".join([*base, alias.name]) for alias in node.names if alias.name != "*"]


def _resolve(root: Path, dotted: str) -> list[Path]:
    if not dotted:
        return []
    base = root.joinpath(*dotted.split("."))
    return [path for path in (base.with_suffix(".py"), base / "__init__.py") if path.is_file()]


def _imports(root: Path, file: Path) -> list[Path]:
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    found: list[Path] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for dotted in _dotted(root, file, node):
                found += _resolve(root, dotted)
    return found


def _on_the_way(root: Path, file: Path) -> list[Path]:
    return [
        init
        for ancestor in file.relative_to(root).parents
        if ancestor.parts and (init := root / ancestor / "__init__.py").is_file()
    ]


def outside(root: Path, module: str) -> list[str]:
    """The paths under *root*, outside the book's own folder, that the book's modules import and so need to load, relative to *root* and sorted. Another service's book is left out."""
    own = _own(root, module)
    if own is None:
        return []
    queue = [path for path in _own_files(root, own) if path.suffix == ".py"]
    seen: set[Path] = set(queue)
    held: set[Path] = set()
    while queue:
        file = queue.pop()
        for path in _imports(root, file):
            if path in seen or not _belongs(root, own, path):
                continue
            seen.add(path)
            queue.append(path)
            held.add(path)
    for path in sorted(held):
        held.update(init for init in _on_the_way(root, path) if not init.is_relative_to(own))
    return sorted(path.relative_to(root).as_posix() for path in held if not path.is_relative_to(own))


def files(root: Path, module: str) -> list[str]:
    """Every file the book needs to load, relative to *root* and sorted: its own folder, then what it imports from outside it."""
    own = _own(root, module)
    if own is None:
        return []
    return sorted({*(path.relative_to(root).as_posix() for path in _own_files(root, own)), *outside(root, module)})


def cmd_files(args: argparse.Namespace, root: str | None) -> int:
    if root is None or _own(Path(root), args.service) is None:
        print(f"{args.service} has no folder under the book root", file=sys.stderr)
        return 2
    for path in (outside if args.outside else files)(Path(root), args.service):
        print(path)
    return 0
