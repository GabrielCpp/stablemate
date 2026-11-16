"""Where each element of the book is implemented in the app, and which of those
files changed since the commit the book was last verified against."""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ostler._vendor.stablemate_core import config as core_config
from ostler.book.contracts import Call, is_openapi, parse, proto_services, rpc_of
from ostler.book.service import Service
from ostler.refs import parse_code_ref


@dataclass
class Report:
    verified: str | None
    head: str
    stale: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    unnamed: dict[str, list[str]] = field(default_factory=dict)
    missing: list[tuple[str, str]] = field(default_factory=list)
    coarse: set[tuple[str, str]] = field(default_factory=set)
    untraced: list[str] = field(default_factory=list)
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
    return (*service.endpoints, *service.records, *service.screens, *service.interactions)


def raw(service: Service[Any]) -> dict[str, tuple[str, ...]]:
    return {e.__name__: tuple(cast(Any, e).source) for e in elements(service)}


def pointer_missing(pointer: str, app_root: str | None, members: dict[str, Path]) -> bool:
    try:
        ref = parse_code_ref(pointer)
    except ValueError:
        return True
    if ref.repository:
        member = members.get(ref.repository)
        return member is None or not os.path.exists(os.path.join(member, ref.path))
    return app_root is not None and not os.path.exists(os.path.join(app_root, ref.path))


def missing(service: Service[Any], app_root: str | None) -> list[tuple[str, str]]:
    members = core_config.workspace_checkouts(Path(app_root) if app_root else Path.cwd())
    found: list[tuple[str, str]] = []
    for name, found_pointers in raw(service).items():
        for pointer in dict.fromkeys(file_of(p) for p in found_pointers):
            if pointer_missing(pointer, app_root, members):
                found.append((name, pointer))
    return found


def traced_in(pointer: str, member: str) -> str | None:
    try:
        ref = parse_code_ref(pointer)
    except ValueError:
        return pointer
    if not ref.repository:
        return pointer
    return pointer.removeprefix(f"repo://{member}/") if ref.repository == member else None


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
    return any(matches(path, p) for p in patterns)


def matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, f"*/{pattern}")


@dataclass
class Missing:
    named: dict[str, list[tuple[str, str]]]
    unnamed: list[str]
    left_out: dict[str, list[str]]
    total: int
    calls: dict[str, list[Call]] = field(default_factory=dict)


def kinds(service: Service[Any]) -> list[tuple[str, type]]:
    return [
        *(("endpoint", e) for e in service.endpoints),
        *(("record", e) for e in service.records),
        *(("screen", e) for e in service.screens),
        *(("interaction", e) for e in service.interactions),
    ]


def missing_files(service: Service[Any], app_root: str, under: tuple[str, ...] = ()) -> Missing:
    assert service.app is not None
    folders = under or service.app.roots
    tracked = [line for line in git(app_root, "ls-files", "--", *folders).splitlines() if line]
    member = core_config.repository_name(Path(app_root))
    namers: dict[str, set[tuple[str, str]]] = {}
    for kind, element in kinds(service):
        for pointer in cast(Any, element).source:
            traced = traced_in(pointer, member)
            if traced is not None:
                namers.setdefault(file_of(traced), set()).add((element.__name__, kind))
    named: dict[str, list[tuple[str, str]]] = {}
    left_out: dict[str, list[str]] = {}
    unnamed: list[str] = []
    for path in sorted(tracked):
        if path in namers:
            named[path] = sorted(namers[path])
        pattern = next((p for p in service.app.ignore if matches(path, p)), None)
        if pattern is not None:
            left_out.setdefault(pattern, []).append(path)
        elif path not in namers:
            unnamed.append(path)
    return Missing(named, unnamed, left_out, len(tracked), undeclared_calls(service, app_root, tracked))


def read(app_root: str, path: str) -> str:
    try:
        with open(os.path.join(app_root, path), encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return ""


def contract_files(service: Service[Any], app_root: str, tracked: list[str]) -> dict[str, str]:
    """The tracked contract files of the book, each with its text: the protos under the roots, the protos
    anywhere in the app that declare a service one of the book's calls names, and the OpenAPI documents under the roots."""
    named = {rpc_of(e).partition("/")[0] for e in service.endpoints if rpc_of(e)}
    found: dict[str, str] = {}
    for path in tracked:
        if path.endswith(".proto"):
            found[path] = read(app_root, path)
        elif path.endswith((".yaml", ".yml", ".json")):
            text = read(app_root, path)
            if is_openapi(text):
                found[path] = text
    if named:
        for path in git(app_root, "ls-files", "*.proto").splitlines():
            text = found.get(path) or read(app_root, path)
            if path not in found and named.intersection(proto_services(text)):
                found[path] = text
    return found


def undeclared_calls(service: Service[Any], app_root: str, tracked: list[str]) -> dict[str, list[Call]]:
    assert service.app is not None
    ignore = service.app.ignore
    declared_rpcs = {rpc_of(e) for e in service.endpoints if rpc_of(e)}
    declared_routes = [(e.method, e.path) for e in service.endpoints if not rpc_of(e)]
    left: dict[str, list[Call]] = {}
    for path, text in sorted(contract_files(service, app_root, tracked).items()):
        if ignored(path, ignore):
            continue
        for call in parse(path, text):
            if ignored(f"{path}::{call.key}", ignore):
                continue
            if call.name in declared_rpcs or any(call.matches(method, route) for method, route in declared_routes):
                continue
            left.setdefault(path, []).append(call)
    return left


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


def stale(service: Service[Any], app_root: str, package_dir: str, since: str | None = None) -> Report:
    verified = since or verified_at(service, package_dir)
    report = Report(verified, head_of(app_root), missing=missing(service, app_root))
    member = core_config.repository_name(Path(app_root))
    pointed: dict[str, tuple[str, ...]] = {}
    for name, found in raw(service).items():
        kept = [(p, traced_in(p, member)) for p in found]
        pointed[name] = tuple(t for _, t in kept if t is not None)
        report.untraced += [p for p, t in kept if t is None and p not in report.untraced]
    if verified is None or service.app is None:
        return report
    changed = changed_since(service, app_root, verified)
    seen: dict[str, set[str]] = {}
    namers: dict[str, list[str]] = {}
    for name, found in pointed.items():
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
    named = {(file_of(p), symbol_of(p)) for found in pointed.values() for p in found if symbol_of(p)}
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
    every = {file_of(p) for found in pointed.values() for p in found}
    report.unnamed = {p: c for p, c in changed.items() if p not in every}
    return report
