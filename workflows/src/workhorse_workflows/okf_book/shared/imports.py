"""Which files a file pulls in, resolved to paths inside the repo, and the walk that unions them."""
from __future__ import annotations

import ast
import re
from collections import deque
from collections.abc import Iterable, Iterator
from pathlib import Path

from ostler.inventory import imports_of
from ostler.refs import is_test_source

_SCRIPT_GRAMMAR = {".ts": "typescript", ".js": "typescript", ".mjs": "typescript",
                   ".tsx": "tsx", ".jsx": "tsx"}
_SCRIPT_TRIES = ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.tsx", "/index.js")
_HTML = frozenset({".html", ".htm"})
_ASSET = re.compile(r"""\b(?:src|href)\s*=\s*["'](?P<ref>[^"'#?]+)""")
_GO_MODULE = re.compile(r"^module\s+(?P<path>\S+)", re.MULTILINE)
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _ancestors(root: Path, start: Path) -> Iterator[Path]:
    """`start`, then each parent of it, up to and including `root`."""
    current = start
    while current.is_relative_to(root):
        yield current
        if current == root:
            return
        current = current.parent


def _python_specs(text: str) -> list[tuple[int, str]]:
    """Each import as (relative level, dotted name), a from-import naming its members as modules too."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    specs: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            specs.extend((0, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module:
                specs.append((node.level, module))
            specs.extend((node.level, f"{module}.{a.name}" if module else a.name) for a in node.names)
    return specs


def _python_module(base: Path, dotted: str) -> list[Path]:
    """The module file `dotted` names under `base`, with the `__init__.py` of every package on the way."""
    parts = dotted.split(".")
    target = base.joinpath(*parts)
    for candidate in (target.with_name(f"{parts[-1]}.py"), target / "__init__.py"):
        if candidate.is_file():
            inits = [base.joinpath(*parts[:i], "__init__.py") for i in range(1, len(parts))]
            return [candidate, *(p for p in inits if p.is_file())]
    return []


def _python_neighbours(root: Path, path: Path) -> list[Path]:
    found: list[Path] = []
    for level, dotted in _python_specs(_text(path)):
        if level:
            base = path.parents[level - 1]
            found.extend(_python_module(base, dotted) if base.is_relative_to(root) else [])
            continue
        for base in _ancestors(root, path.parent):
            resolved = _python_module(base, dotted)
            if resolved:
                found.extend(resolved)
                break
    return found


def _go_package(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*.go") if not p.name.endswith("_test.go"))


def _go_module(root: Path, path: Path) -> tuple[Path, str] | None:
    for folder in _ancestors(root, path.parent):
        mod = folder / "go.mod"
        if mod.is_file():
            match = _GO_MODULE.search(_text(mod))
            return (folder, match.group("path")) if match else None
    return None


def _go_neighbours(root: Path, path: Path) -> list[Path]:
    found = _go_package(path.parent)
    module = _go_module(root, path)
    if module is None:
        return found
    folder, name = module
    for spec in imports_of(path, _text(path), language="go"):
        if spec.startswith(f"{name}/"):
            found.extend(_go_package(folder / spec.removeprefix(f"{name}/")))
    return found


def _script_file(base: Path) -> Path | None:
    for suffix in _SCRIPT_TRIES:
        candidate = Path(f"{base}{suffix}")
        if candidate.is_file():
            return candidate
    return None


def _script_neighbours(path: Path) -> list[Path]:
    grammar = _SCRIPT_GRAMMAR[path.suffix]
    found: list[Path] = []
    for spec in imports_of(path, _text(path), language=grammar):
        if spec.startswith("."):
            resolved = _script_file(path.parent / spec)
            if resolved is not None:
                found.append(resolved)
    return found


def _html_neighbours(path: Path) -> list[Path]:
    found: list[Path] = []
    for match in _ASSET.finditer(_text(path)):
        ref = match.group("ref").strip()
        if not ref or ref.startswith("/") or _SCHEME.match(ref):
            continue
        candidate = path.parent / ref
        if candidate.is_file():
            found.append(candidate)
    return found


def neighbours(root: Path, path: Path) -> list[Path]:
    """The files `path` imports or loads, as found and not yet resolved."""
    suffix = path.suffix
    if suffix == ".py":
        return _python_neighbours(root, path)
    if suffix == ".go":
        return _go_neighbours(root, path)
    if suffix in _SCRIPT_GRAMMAR:
        return _script_neighbours(path)
    if suffix in _HTML:
        return _html_neighbours(path)
    return []


def reached_files(root: Path, starts: Iterable[str]) -> tuple[str, ...]:
    """Every production file an import path from one of `starts` reaches, nearest first, repo-relative."""
    base = root.resolve()
    queue = deque(base / start for start in starts)
    met: set[Path] = set()
    seen: dict[Path, str] = {}
    while queue:
        found = queue.popleft()
        if found in met:
            continue
        met.add(found)
        path = found.resolve()
        rel = path.relative_to(base).as_posix() if path.is_relative_to(base) else ""
        if path in seen or not rel or not path.is_file() or is_test_source(rel):
            continue
        seen[path] = rel
        queue.extend(neighbour for neighbour in neighbours(base, path) if neighbour not in met)
    return tuple(seen.values())
