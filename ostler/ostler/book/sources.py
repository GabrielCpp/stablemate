"""Where each element of the book is implemented in the app, and which of those
files changed since the commit the book was last verified against."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, cast

from ostler.book.service import Service


@dataclass
class Report:
    verified: str | None
    head: str
    stale: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    unnamed: dict[str, list[str]] = field(default_factory=dict)
    missing: list[tuple[str, str]] = field(default_factory=list)
    coarse: set[tuple[str, str]] = field(default_factory=set)
    beside: dict[str, tuple[list[str], list[str]]] = field(default_factory=dict)
    functions: dict[str, dict[str, list[str]]] = field(default_factory=dict)

    @property
    def open(self) -> bool:
        return bool(self.unnamed or self.functions or self.missing)


def file_of(pointer: str) -> str:
    return pointer.split("::", 1)[0]


def symbol_of(pointer: str) -> str | None:
    return pointer.split("::", 1)[1].rsplit(".", 1)[-1] if "::" in pointer else None


def elements(service: Service[Any]) -> tuple[type, ...]:
    return (*service.endpoints, *service.records)


def raw(service: Service[Any]) -> dict[str, tuple[str, ...]]:
    return {e.__name__: tuple(cast(Any, e).source) for e in elements(service)}


def pointers(service: Service[Any]) -> dict[str, tuple[str, ...]]:
    return {name: tuple(dict.fromkeys(file_of(p) for p in found)) for name, found in raw(service).items()}


def missing(service: Service[Any], app_root: str) -> list[tuple[str, str]]:
    return [(name, path) for name, paths in pointers(service).items() for path in paths
            if not os.path.exists(os.path.join(app_root, path))]


def verified_at(service: Service[Any], package_dir: str) -> str | None:
    if service.app is None:
        return None
    try:
        with open(os.path.join(package_dir, service.app.verified)) as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def git(app_root: str, *args: str) -> str:
    return subprocess.run(["git", "-C", app_root, *args], check=True, capture_output=True, text=True).stdout


def head_of(app_root: str) -> str:
    return git(app_root, "rev-parse", "--short", "HEAD").strip()


def ignored(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, f"*/{p}") for p in patterns)


DEFINITIONS = (
    re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)"),
    re.compile(r"^\s*(?:async\s+)?def\s+(\w+)"),
    re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*(\w+)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\("),
    re.compile(r"^\s*(?:static\s+|async\s+|public\s+|private\s+|protected\s+|override\s+)*(?:[\w<>?,\[\]]+\s+)?(\w+)\s*\([^;]*\)\s*(?:async\s*)?(?:\{|=>|$)"),
)
NOT_NAMES = {"if", "for", "while", "switch", "return", "catch", "func", "function", "else"}


def defined(line: str, loose: bool = False) -> str | None:
    for pattern in DEFINITIONS if loose else DEFINITIONS[:-1]:
        m = pattern.match(line)
        if m and m.group(1) not in NOT_NAMES:
            return m.group(1)
    return None


def changed_functions(app_root: str, commit: str, path: str) -> set[str] | None:
    out = git(app_root, "diff", "-U0", f"{commit}..HEAD", "--", path)
    names: set[str] = set()
    for hunk in re.split(r"^@@", out, flags=re.M)[1:]:
        head, _, body = hunk.partition("\n")
        inside = [defined(line[1:]) for line in body.splitlines() if line[:1] in "+-"]
        found = {n for n in inside if n}
        context = defined(head.split("@@", 1)[-1].lstrip(), loose=True)
        if context:
            found.add(context)
        if not found:
            return None
        names |= found
    return names


def changed_since(service: Service[Any], app_root: str, commit: str) -> dict[str, list[str]]:
    assert service.app is not None
    out = git(app_root, "log", "--format=commit %h", "--name-only", f"{commit}..HEAD", "--", *service.app.roots)
    changed: dict[str, list[str]] = {}
    current = ""
    for line in out.splitlines():
        if line.startswith("commit "):
            current = line.split(" ", 1)[1]
        elif line.strip() and not ignored(line, service.app.ignore):
            changed.setdefault(line, []).append(current)
    return changed


def symbol_commits(app_root: str, commit: str, pointer: str) -> list[str] | None:
    symbol = symbol_of(pointer)
    for pattern in (f"func .*\\b{symbol}(", f"type {symbol} "):
        try:
            out = git(app_root, "log", "--format=commit %h", "-s", "-L", f":{pattern}:{file_of(pointer)}", f"{commit}..HEAD")
        except subprocess.CalledProcessError:
            continue
        return [line.split(" ", 1)[1] for line in out.splitlines() if line.startswith("commit ")]
    return None


def stale(service: Service[Any], app_root: str, package_dir: str) -> Report:
    verified = verified_at(service, package_dir)
    report = Report(verified, head_of(app_root), missing=missing(service, app_root))
    if verified is None or service.app is None:
        return report
    changed = changed_since(service, app_root, verified)
    seen: dict[str, set[str]] = {}
    namers: dict[str, list[str]] = {}
    for name, found in raw(service).items():
        for pointer in found:
            path = file_of(pointer)
            if path not in changed:
                continue
            if name not in namers.setdefault(path, []):
                namers[path].append(name)
            commits = symbol_commits(app_root, verified, pointer) if symbol_of(pointer) else None
            if commits is None:
                commits = changed[path]
                if symbol_of(pointer):
                    report.coarse.add((name, pointer))
            seen.setdefault(path, set()).update(commits)
            if commits:
                report.stale.setdefault(name, {})[pointer] = commits
    named = {(file_of(p), symbol_of(p)) for found in raw(service).values() for p in found if symbol_of(p)}
    for path, names in namers.items():
        functions = changed_functions(app_root, verified, path)
        if functions is None:
            rest = [c for c in changed[path] if c not in seen[path]]
            if rest:
                report.beside[path] = (rest, names)
            continue
        for function in sorted(functions):
            if (path, function) in named or ignored(f"{path}::{function}", service.app.ignore):
                continue
            commits = symbol_commits(app_root, verified, f"{path}::{function}") or changed[path]
            report.functions.setdefault(path, {})[function] = commits
    every = {file_of(p) for found in raw(service).values() for p in found}
    report.unnamed = {p: c for p, c in changed.items() if p not in every}
    return report
