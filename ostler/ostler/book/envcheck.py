"""Static check that a book pins no environment-issued identifiers or cloud resources."""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ostler.book.files import files as book_files, outside as imported_outside, service_folder

if TYPE_CHECKING:
    from ostler.book.check import Finding

ARN_RE = re.compile(r"\barn:aws(?:-cn|-us-gov)?:[a-z0-9-]+:[a-z0-9-]*:\d{0,12}:[^\s\"'`]+")
STORAGE_URI_RE = re.compile(r"\b(?:s3|gs|az)://[a-zA-Z0-9._-][^\s\"'`]*")
AWS_BACKING_RE = re.compile(
    r"\b(?:[a-z0-9.-]+\.)?(?:s3|sqs|sns|events|dynamodb|secretsmanager|kms|sts|iam|rds|ecr)"
    r"(?:-[a-z0-9]+)?\.[a-z0-9.-]*amazonaws\.com\b",
    re.IGNORECASE,
)
AWS_RESOURCE_ID_RE = re.compile(
    r"\b(?:(?:vpc|subnet|sg|igw|rtb|eni|ami|vol|snap|nat|eipalloc|pcx|vpce|tgw)-[0-9a-f]{8,17}|i-[0-9a-f]{8,17})\b"
)
AWS_KEY_ID_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
ULID_RE = re.compile(r"\b0[0-7][0-9A-HJKMNP-TV-Z]{24}\b")
CLOUD_HOST_RE = re.compile(
    r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:amazonaws\.com|aws\.amazon\.com|cloudfront\.net|azurewebsites\.net|run\.app)\b",
    re.IGNORECASE,
)
URL_RE = re.compile(r"\bhttps?://[^\s\"'<>`]+", re.IGNORECASE)

RESERVED_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "example.com", "example.org", "example.net"})
RESERVED_SUFFIXES = (".localhost", ".local", ".test", ".invalid", ".example", ".example.com", ".example.org", ".example.net")
HOST_DECLARATIONS = frozenset({"Environment", "Documentation"})


def _reserved_host(host: str | None) -> bool:
    if not host:
        return True
    lowered = host.lower().strip("[]")
    return lowered in RESERVED_HOSTS or lowered.endswith(RESERVED_SUFFIXES)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _callee_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _mark_subtree(node: ast.AST, target: set[int]) -> None:
    for child in ast.walk(node):
        target.add(id(child))


def _direct_allowed(tree: ast.Module) -> set[int]:
    allowed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _callee_name(node.func) in HOST_DECLARATIONS:
            _mark_subtree(node, allowed)
        elif isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "source" for t in node.targets):
            _mark_subtree(node.value, allowed)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "source" and node.value:
            _mark_subtree(node.value, allowed)
    return allowed


def _top_values(tree: ast.Module) -> dict[str, ast.AST]:
    values: dict[str, ast.AST] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            values[stmt.targets[0].id] = stmt.value
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value is not None:
            values[stmt.target.id] = stmt.value
    return values


def _imported_uses(tree: ast.Module, allowed: set[int]) -> dict[str, list[bool]]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    uses: dict[str, list[bool]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in aliases:
            uses.setdefault(aliases[node.id], []).append(id(node) in allowed)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            uses.setdefault(node.attr, []).append(id(node) in allowed)
    return uses


def _allowed_url_nodes(tree: ast.Module, outside_uses: dict[str, list[bool]] | None = None) -> set[int]:
    allowed = _direct_allowed(tree)
    top_values = _top_values(tree)
    loads: dict[str, list[bool]] = {name: [] for name in top_values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in loads:
            loads[node.id].append(id(node) in allowed)
    for name, value in top_values.items():
        uses = loads[name] + (outside_uses or {}).get(name, [])
        if uses and all(uses):
            _mark_subtree(value, allowed)
    return allowed


def _scan_text(text: str, allow_urls: bool, templated: bool = False) -> list[str]:
    problems: list[str] = []
    for match in ARN_RE.finditer(text):
        problems.append(f"hardcodes AWS ARN {match.group(0)!r}: resolve environment resources through the surface or Reference instead")
    for match in STORAGE_URI_RE.finditer(text):
        problems.append(f"hardcodes cloud storage URI {match.group(0)!r}: pass bucket or object locations through the surface or Reference instead")
    for match in AWS_BACKING_RE.finditer(text):
        problems.append(f"hardcodes AWS resource endpoint {match.group(0)!r}: backing cloud services belong in the runtime or surface, not in the book")
    for match in AWS_RESOURCE_ID_RE.finditer(text):
        problems.append(f"hardcodes AWS resource id {match.group(0)!r}: resolve environment resources at runtime instead")
    for match in AWS_KEY_ID_RE.finditer(text):
        problems.append(f"hardcodes AWS access key id {match.group(0)!r}: keep credentials out of the book")
    for match in UUID_RE.finditer(text):
        problems.append(
            f"hardcodes UUID {match.group(0)!r}: resolve environment ids with Reference or learn them from replies, and mint unknown ids with uuid4()"
        )
    for match in ULID_RE.finditer(text):
        hit = match.group(0)
        if any(ch.isdigit() for ch in hit[2:]):
            problems.append(f"hardcodes ULID {hit!r}: resolve environment ids with Reference or learn them from replies")
    if allow_urls:
        return problems
    reported_hosts: set[str] = set()
    for match in URL_RE.finditer(text):
        raw_url = match.group(0).rstrip(".,;:)")
        host = urlsplit(raw_url).hostname
        if templated and host == "placeholder":
            continue
        if not _reserved_host(host):
            if host:
                reported_hosts.add(host.lower())
            problems.append(
                f"hardcodes URL {raw_url!r} outside Environment: declare environment hosts in Environment and pass them through the surface or Reference"
            )
    for match in CLOUD_HOST_RE.finditer(text):
        host = match.group(0)
        if host.lower() not in reported_hosts and not AWS_BACKING_RE.fullmatch(host):
            problems.append(f"hardcodes cloud endpoint {host!r} outside Environment: declare environment hosts in Environment instead")
    return problems


def _joined_skeleton(node: ast.JoinedStr) -> tuple[str, str]:
    rendered: list[str] = []
    display: list[str] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            rendered.append(part.value)
            display.append(part.value)
        else:
            rendered.append("placeholder")
            display.append("{...}")
    return "".join(rendered), "".join(display)


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return None


def _file_faults(label: str, tree: ast.Module, outside_uses: dict[str, list[bool]]) -> list[Finding]:
    from ostler.book.check import Finding

    docstrings = _docstring_nodes(tree)
    allowed_urls = _allowed_url_nodes(tree, outside_uses)
    joined_children = {id(part) for node in ast.walk(tree) if isinstance(node, ast.JoinedStr) for part in node.values}
    seen: set[tuple[int, str]] = set()
    out: list[Finding] = []
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings and id(node) not in joined_children:
            for problem in _scan_text(node.value, id(node) in allowed_urls):
                if (lineno, problem) not in seen:
                    seen.add((lineno, problem))
                    out.append(Finding(f"{label}:{lineno}", problem))
        elif isinstance(node, ast.JoinedStr):
            skeleton, display = _joined_skeleton(node)
            for problem in _scan_text(skeleton, id(node) in allowed_urls, templated=True):
                shown = problem.replace("placeholder", "{...}") if "{...}" in display else problem
                if (lineno, shown) not in seen:
                    seen.add((lineno, shown))
                    out.append(Finding(f"{label}:{lineno}", shown))
    return sorted(out, key=lambda f: f.name)


def _candidate_files(module: str) -> list[tuple[str, Path]]:
    from ostler.book.index import book_root

    cwd = Path(os.getcwd()).resolve()
    roots = [cwd]
    try:
        configured = Path(book_root(str(cwd))).resolve()
        if configured not in roots:
            roots.append(configured)
    except Exception:
        pass
    for root in roots:
        if service_folder(root, module) is not None:
            return [(rel, root / rel) for rel in book_files(root, module) if rel.endswith(".py")]
    candidates: list[tuple[str, Path]] = []
    for name, loaded in sorted(sys.modules.items()):
        if name != module and not name.startswith(module + "."):
            continue
        raw_file = getattr(loaded, "__file__", None)
        if not raw_file or not raw_file.endswith(".py"):
            continue
        file_path = Path(raw_file).resolve()
        if file_path.name.startswith("test_"):
            continue
        base = next((r for r in roots if file_path.is_relative_to(r)), None)
        label = file_path.relative_to(base).as_posix() if base is not None else name
        candidates.append((label, file_path))
    return candidates


def environment_faults(module: str) -> list[Finding]:
    parsed = [(label, tree) for label, path in _candidate_files(module) if (tree := _parse(path)) is not None]
    uses_by_file = [_imported_uses(tree, _direct_allowed(tree)) for _, tree in parsed]
    out: list[Finding] = []
    for index, (label, tree) in enumerate(parsed):
        outside: dict[str, list[bool]] = {}
        for other, uses in enumerate(uses_by_file):
            if other != index:
                for name, flags in uses.items():
                    outside.setdefault(name, []).extend(flags)
        out.extend(_file_faults(label, tree, outside))
    return out


def outside_notes(module: str) -> list[Finding]:
    from ostler.book.check import Finding
    from ostler.book.index import book_root

    root = book_root(os.getcwd())
    held = imported_outside(Path(root), module)
    if not held:
        return []
    return [
        Finding(
            "files",
            f"the book imports {len(held)} file(s) outside its folder: {', '.join(held)}; a commit of the book takes them with it",
            told=True,
        )
    ]
