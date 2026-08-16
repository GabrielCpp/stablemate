#!/usr/bin/env python3
"""Guard the portability tiers. Wired into `make test`.

The published packages — the ones a user `pip install`s — have to run on Linux, macOS
and Windows. Nothing in this repo's loop proves that: the container is Ubuntu and CI is
`ubuntu-latest`, so a POSIX-only call in a shipped package fails for the first person on
a Mac or a Windows box and for nobody here.

So this flags the non-portable APIs *inside tier-1 source* and names the portable
replacement. Process supervision (tier 2) and the container harness (tier 3) genuinely
need these calls; each such site is declared in `ALLOWED` with its reason, and the
reasons print on any failure. The tiers, the replacement table and the rule that a
platform branch owes a test on both sides live in the `portability` skill (base-library).

**What this is not.** It is an API denylist, not a portability proof. It cannot tell you
that a subprocess behaves differently elsewhere, that a path built at runtime is absolute
on one OS only, or that a file left open blocks a delete on Windows. It knows the shapes
that have gone wrong. The only proof is running the suite on the platform, and nothing
here does that yet.

This script installs beside the `portability` skill, so it runs in any repo that publishes
a package. Which import roots are tier 1, and which sites genuinely need POSIX, are that
repo's to state — see `[check-portability]` in `.agent-checks.toml`.

Run:
    uv run python <this script> [--root DIR]
"""

from __future__ import annotations

import argparse
import ast
import sys
import tomllib
from pathlib import Path

#: Repo-local declarations, read from the root of whatever repo is being checked.
CONFIG = ".agent-checks.toml"
TABLE = "check-portability"

#: `os.<name>` calls that do not exist on Windows.
POSIX_OS_CALLS = frozenset({
    "getuid", "geteuid", "getgid", "getegid", "setuid", "setgid", "setegid", "seteuid",
    "umask", "fork", "forkpty", "killpg", "getpgid", "getpgrp", "setpgid", "setpgrp",
    "setsid", "getppid", "nice", "chown", "chroot", "mkfifo",
})

#: `signal.<name>` members absent on Windows. SIGTERM/SIGINT/SIGBREAK are portable.
POSIX_SIGNALS = frozenset({
    "SIGKILL", "SIGUSR1", "SIGUSR2", "SIGHUP", "SIGQUIT", "SIGPIPE", "SIGALRM",
    "SIGCHLD", "SIGCONT", "SIGSTOP", "SIGTSTP", "SIGWINCH",
})

#: subprocess keywords with no Windows equivalent.
POSIX_SUBPROCESS_KWARGS = frozenset({"start_new_session", "preexec_fn", "restore_signals"})

#: Absolute paths that only exist on a Unix. `tempfile` and `platformdirs` are the
#: portable answers; both are already dependencies here.
#:
#: `/dev/` is deliberately absent. Its first run flagged eleven sites and every one was
#: correct: ten were git's diff sentinel — `--name-status` prints the literal `/dev/null`
#: for the missing side of an add or a delete, a token in git's output format that reads
#: the same on Windows — and the eleventh was a path *inside* an alpine container, whose
#: platform is Linux whatever the host is. A rule whose every hit is a false positive
#: teaches people to ignore the checker, so the redirect case it was meant to catch is
#: left to the `shell=` rule, which is where an actual `2>/dev/null` lives.
UNIX_PATH_PREFIXES = ("/tmp", "/var/", "/etc/", "/usr/", "/opt/", "/proc/")

def declarations(root: Path) -> dict:
    """What *root*'s repo declares to this check, from its `.agent-checks.toml`.

    The script travels with its skill, so which import roots ship to users and which
    supervision sites earned their POSIX call belong to the repo rather than to the rule.
    A repo that declares no tier 1 publishes nothing, which is a pass and not a finding.
    """
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
        # os.<posix-only>(...) and signal.<posix-only>
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

        # subprocess(..., start_new_session=True) and friends
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in POSIX_SUBPROCESS_KWARGS:
                    problems.append(
                        f"{rel}:{node.lineno} {kw.arg}= is POSIX-only; Windows needs "
                        f"creationflags instead"
                    )

        # a hardcoded Unix absolute path
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
            continue  # ruff owns syntax; this pass owns portability
        scanned += 1
        problems.extend(_findings(tree, rel))

    # An exemption over a module that is gone, or that no longer makes a POSIX-only call,
    # excuses nothing while reading as though it still does.
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
