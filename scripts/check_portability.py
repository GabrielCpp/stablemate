#!/usr/bin/env python3
"""Guard the portability tiers."""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

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

POSIX_SUBPROCESS_KWARGS = frozenset({"start_new_session", "preexec_fn", "restore_signals"})

UNIX_PATH_PREFIXES = ("/tmp", "/var/", "/etc/", "/usr/", "/opt/", "/proc/")

def declarations(root: Path) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`."""
    config = root / CONFIG
    if not config.is_file():
        return {}
    return tomllib.loads(config.read_text(encoding="utf-8")).get(TABLE, {})


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
        if rel in allowed:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        scanned += 1
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help=f"repo holding {CONFIG} (default: cwd)"
    )
    args = parser.parse_args()

    allowed: dict[str, str] = declarations(args.root).get("allow", {})
    problems = check_portability(args.root)
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
