"""Which definitions of the book use a changed module-level name, read with `ast` over the files of the book.

Each top-level class, function and assignment of a file is a definition with the identifiers its source mentions. A
changed name reaches the definitions that mention it and can see it: in the same module, through `from m import N`
(a package that re-exports it counts), or as `alias.N` of a module alias. The walk goes on through the reached
definitions to a fixed point and stops at the classes the caller names as elements. What it cannot trace (a star
import, `getattr` or `globals()`) is reported as a reason, never guessed."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Callable

DYNAMIC = ("getattr", "globals")


def simple_targets(target: ast.expr) -> list[str] | None:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        found: list[str] = []
        for element in target.elts:
            inner = simple_targets(element)
            if inner is None:
                return None
            found += inner
        return found
    return None


def named(node: ast.stmt) -> list[str] | None:
    """The names a top-level statement defines when it is a class, a function or an assignment to simple names, else None."""
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return [node.name]
    if isinstance(node, ast.Assign):
        found: list[str] = []
        for target in node.targets:
            inner = simple_targets(target)
            if inner is None:
                return None
            found += inner
        return found
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return None


def chain_of(node: ast.expr) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    return ".".join([node.id, *reversed(parts)])


@dataclass
class Definition:
    kind: str
    idents: set[str] = field(default_factory=set)
    attrs: set[tuple[str, str]] = field(default_factory=set)


@dataclass
class Source:
    path: str
    module: str
    package: bool
    defs: dict[str, Definition] = field(default_factory=dict)
    binds: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    plain: set[str] = field(default_factory=set)
    stars: list[str] = field(default_factory=list)
    exports: set[str] = field(default_factory=set)
    dynamic: bool = False


def absolute(source: Source, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    parts = source.module.split(".") if source.module else []
    if not source.package:
        parts = parts[:-1]
    parts = parts[: len(parts) - (node.level - 1)] if node.level > 1 else parts
    return ".".join([*parts, *(node.module.split(".") if node.module else [])])


def read_imports(source: Source, node: ast.stmt) -> None:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname:
                source.binds[alias.asname] = (alias.name, None)
            else:
                source.plain.add(alias.name)
                source.binds[alias.name.split(".")[0]] = (alias.name.split(".")[0], None)
    elif isinstance(node, ast.ImportFrom):
        where = absolute(source, node)
        for alias in node.names:
            if alias.name == "*":
                source.stars.append(where)
            else:
                source.binds[alias.asname or alias.name] = (where, alias.name)


def read_exports(node: ast.stmt) -> set[str]:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
        if isinstance(node.value, (ast.List, ast.Tuple)):
            return {e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


def read_source(path: str, module: str, text: str) -> Source | None:
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    source = Source(path, module, path.endswith("__init__.py"))
    for node in tree.body:
        read_imports(source, node)
        source.exports |= read_exports(node)
        defined = named(node)
        if defined is None:
            continue
        kind = "class" if isinstance(node, ast.ClassDef) else "name"
        for name in defined:
            found = source.defs.setdefault(name, Definition(kind))
            for inner in ast.walk(node):
                if isinstance(inner, ast.Name):
                    found.idents.add(inner.id)
                elif isinstance(inner, ast.Attribute):
                    chain = chain_of(inner)
                    if chain is not None and "." in chain:
                        prefix, _, attr = chain.rpartition(".")
                        found.attrs.add((prefix, attr))
    for inner in ast.walk(tree):
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id in DYNAMIC:
            source.dynamic = True
    return source


@dataclass
class Reach:
    hits: list[tuple[str, str, str]] = field(default_factory=list)
    used: bool = False
    hidden: str = ""


class Graph:
    def __init__(self, sources: list[Source]) -> None:
        self.sources = sources
        self.by_module = {s.module: s for s in sources}

    def alias(self, source: Source, prefix: str) -> str | None:
        if prefix in source.plain:
            return prefix
        head, _, rest = prefix.partition(".")
        bound = source.binds.get(head)
        if bound is None:
            return None
        where, name = bound
        found = where if name is None else f"{where}.{name}" if f"{where}.{name}" in self.by_module else None
        if found is None:
            return None
        return f"{found}.{rest}" if rest else found

    def seen_as(self, origin: tuple[str, str]) -> set[tuple[str, str]]:
        found = {origin}
        grew = True
        while grew:
            grew = False
            for source in self.sources:
                for local, (where, name) in source.binds.items():
                    if name is not None and (where, name) in found and (source.module, local) not in found:
                        found.add((source.module, local))
                        grew = True
        return found

    def users(self, origin: tuple[str, str]) -> list[tuple[Source, str]]:
        origins = self.seen_as(origin)
        found: list[tuple[Source, str]] = []
        for source in self.sources:
            for name, definition in source.defs.items():
                if (source.module, name) == origin:
                    continue
                if any(self.sees(source, ident, origins) for ident in definition.idents) or any(
                    (self.alias(source, prefix), attr) in origins for prefix, attr in definition.attrs
                ):
                    found.append((source, name))
        return found

    def sees(self, source: Source, ident: str, origins: set[tuple[str, str]]) -> bool:
        bound = source.binds.get(ident)
        if bound is not None and bound[1] is not None and bound in origins:
            return True
        return bound is None and (source.module, ident) in origins

    def untraced(self, origin: tuple[str, str], label: str) -> str:
        origins = self.seen_as(origin)
        modules = {m for m, _ in origins}
        for source in self.sources:
            for where in source.stars:
                owner = self.by_module.get(where)
                if where == origin[0] or (where in modules and owner is not None and origin[1] in owner.exports):
                    return f"{label} is star-imported from {where} in {source.path}"
        for source in self.sources:
            if source.dynamic and (source.module in modules or any(w in modules for w, _ in source.binds.values())):
                return f"{source.path} reads names with getattr or globals() and can see {label}"
        return ""

    def reach(self, module: str, name: str, element: Callable[[str, str], bool]) -> Reach:
        found = Reach()
        found.hidden = self.untraced((module, name), name)
        parents: dict[tuple[str, str], tuple[str, str] | None] = {(module, name): None}
        queue = [(module, name)]
        while queue:
            here = queue.pop(0)
            for source, user in self.users(here):
                key = (source.module, user)
                if key in parents:
                    continue
                found.used = True
                parents[key] = here
                if source.defs[user].kind == "class" and element(source.module, user):
                    steps = [user]
                    step = parents[key]
                    while step is not None and step != (module, name):
                        steps.append(step[1])
                        step = parents[step]
                    found.hits.append((source.module, user, " <- used by ".join([name, *reversed(steps)])))
                else:
                    queue.append(key)
        return found
