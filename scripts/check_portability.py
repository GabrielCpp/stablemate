#!/usr/bin/env python3
"""Guard the portability tiers."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from pathlib import Path

import guards

CONFIG = ".agent-checks.toml"
TABLE = "check-portability"

POSIX_OS_CALLS = frozenset({
    "getuid", "geteuid", "getgid", "getegid", "setuid", "setgid", "setegid", "seteuid",
    "umask", "fork", "forkpty", "killpg", "getpgid", "getpgrp", "setpgid", "setpgrp",
    "setsid", "getppid", "nice", "chown", "chroot", "mkfifo",
})

POSIX_SIGNALS = frozenset({
    "SIGKILL", "SIGUSR1", "SIGUSR2", "SIGHUP", "SIGQUIT", "SIGPIPE", "SIGALRM",
    "SIGCHLD", "SIGCONT", "SIGSTOP", "SIGTSTP", "SIGWINCH",
})

POSIX_MODULES = frozenset({
    "fcntl", "termios", "pwd", "grp", "resource", "pty", "tty", "posix", "syslog", "crypt",
})

MISSING_NAME_ERRORS = frozenset({
    "AttributeError", "ImportError", "ModuleNotFoundError", "Exception", "BaseException",
})

POSIX_SUBPROCESS_KWARGS = frozenset({"start_new_session", "preexec_fn", "restore_signals"})

UNIX_PATH_PREFIXES = ("/tmp", "/var/", "/etc/", "/usr/", "/opt/", "/proc/")

def declarations(root: Path) -> dict:
    return guards.declarations(root, CONFIG, TABLE)


def _tier1_modules(root: Path, tier1: list[str]) -> list[Path]:
    modules: list[Path] = []
    for relative in tier1:
        base = root / relative
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            parts = set(path.parts)
            if "_vendor" in parts or "__pycache__" in parts or ".venv" in parts:
                continue
            modules.append(path)
    return modules


def _imported_modules(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if node.level == 0 and node.module:
        return [node.module.split(".")[0]]
    return []


def _findings(tree: ast.AST, rel: str) -> list[str]:
    """Non-portable API uses in one module, as human-readable problems."""
    problems: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            owner, name = node.value.id, node.attr
            if owner == "os" and name in POSIX_OS_CALLS:
                problems.append(
                    f"{rel}:{node.lineno} os.{name}() does not exist on Windows"
                )
            elif owner == "signal" and name in POSIX_SIGNALS:
                problems.append(
                    f"{rel}:{node.lineno} signal.{name} does not exist on Windows "
                    f"(SIGTERM/SIGINT do)"
                )

        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for module in _imported_modules(node):
                if module in POSIX_MODULES:
                    problems.append(f"{rel}:{node.lineno} {module} does not exist on Windows")

        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in POSIX_SUBPROCESS_KWARGS:
                    problems.append(
                        f"{rel}:{node.lineno} {kw.arg}= is POSIX-only; Windows needs "
                        f"creationflags instead"
                    )

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if text.startswith(UNIX_PATH_PREFIXES) and len(text) > 5:
                problems.append(
                    f"{rel}:{node.lineno} hardcoded {text!r} — use tempfile or "
                    f"platformdirs, which already answer per platform"
                )

    return problems


def _is_platform_test(test: ast.expr) -> bool:
    for node in ast.walk(test):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and (node.value.id, node.attr) in {("sys", "platform"), ("os", "name")}
        ):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "hasattr"
        ):
            return True
    return False


def _catches_missing_name(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    return any(isinstance(name, ast.Name) and name.id in MISSING_NAME_ERRORS for name in names)


def _import_time_nodes(body: list[ast.stmt]) -> Iterator[ast.AST]:
    """The parts of *body* Python evaluates on import, outside any platform guard."""
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from stmt.decorator_list
            yield from stmt.args.defaults
            yield from (default for default in stmt.args.kw_defaults if default is not None)
        elif isinstance(stmt, ast.If) and _is_platform_test(stmt.test):
            continue
        elif isinstance(stmt, ast.Try) and any(map(_catches_missing_name, stmt.handlers)):
            yield from _import_time_nodes(stmt.orelse)
            yield from _import_time_nodes(stmt.finalbody)
        else:
            for _field, value in ast.iter_fields(stmt):
                if isinstance(value, list) and value and isinstance(value[0], ast.stmt):
                    yield from _import_time_nodes(value)
                elif isinstance(value, list):
                    yield from (item for item in value if isinstance(item, ast.AST))
                elif isinstance(value, ast.AST):
                    yield value
            if isinstance(stmt, (ast.Import, ast.ImportFrom)):
                yield stmt


def _import_time_findings(tree: ast.Module, rel: str) -> list[str]:
    """POSIX-only names a module reads on import, which no allow entry can excuse."""
    return [
        f"{problem} (read at import, so the module cannot load there and its allow entry "
        f"does not excuse it)"
        for node in _import_time_nodes(tree.body)
        for problem in _findings(node, rel)
    ]


def check_portability(root: Path) -> list[str]:
    declared = declarations(root)
    tier1: list[str] = declared.get("tier1", [])
    if not tier1:
        print(f"ok: no [{TABLE}] tier1 declared in {CONFIG} — nothing ships, nothing to scan")
        return []

    allowed: dict[str, str] = declared.get("allow", {})
    problems: list[str] = []
    scanned = 0
    for path in _tier1_modules(root, tier1):
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        scanned += 1
        if rel in allowed:
            problems.extend(_import_time_findings(tree, rel))
        else:
            problems.extend(_findings(tree, rel))

    for rel, _why in allowed.items():
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: excused in {CONFIG}, but the module no longer exists")
        elif not _findings(ast.parse(path.read_text(encoding="utf-8")), rel):
            problems.append(
                f"{rel}: excused in {CONFIG}, but it makes no POSIX-only call any more — "
                f"delete the entry"
            )

    if not problems:
        print(
            f"ok: no POSIX-only API in {scanned} shipped modules "
            f"({len(allowed)} declared process-supervision sites)"
        )
    return problems


def main() -> int:
    root = guards.root_argument(__doc__, CONFIG)

    allowed: dict[str, str] = declarations(root).get("allow", {})
    problems = check_portability(root)
    if not problems:
        return 0
    print("\nFAIL check_portability:", file=sys.stderr)
    for problem in problems:
        print(f"  {problem}", file=sys.stderr)
    print(
        "\nThese packages ship to PyPI, so the platform is the user's choice, not ours — "
        "and nothing in this repo's CI would catch it. See the `stablemate-portability` "
        "skill for the three tiers, the portable replacement for each API, and how to "
        "declare a site that genuinely needs POSIX.",
        file=sys.stderr,
    )
    if allowed:
        print("\nAlready declared:", file=sys.stderr)
        for path, why in sorted(allowed.items()):
            print(f"  {path} — {why.strip()}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
