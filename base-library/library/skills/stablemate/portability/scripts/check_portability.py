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

Run:
    uv run python base-library/library/skills/stablemate/portability/scripts/check_portability.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _repo_root() -> Path:
    """The repo being checked, found by ascent rather than by a fixed depth.

    This script installs beside its skill, so how deep it sits under the repo is the
    library's layout and not this rule's — a `parents[N]` was true only while it lived in
    `<repo>/scripts/`, and went silently wrong the moment the skill carried it elsewhere.
    Ascending to the working copy's own marker is the one form that survives the move.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / ".git").exists():
            return candidate
    return Path.cwd()


REPO = _repo_root()

#: Tier 1 — shipped to PyPI, so a user's platform is not ours to choose. Each entry is
#: the package's import root; tests are excluded (a test for a tier-2 module is
#: legitimately POSIX, and skipping them keeps this a source rule).
TIER1_SOURCE = (
    "core/stablemate_core",
    "farrier/farrier",
    "ostler/ostler",
    "groom/groom",
    "saddlebag/saddlebag",
    "workhorse/workhorse",
    "workflows/src/workhorse_workflows",
)

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

#: Declared tier-2 (POSIX process supervision) and tier-3 (Linux container harness)
#: sites. Keyed by repo-relative path; the reason prints on any failure so the next
#: person sees why these are exempt and the one they just wrote is not.
ALLOWED: dict[str, str] = {
    "workhorse/workhorse/runner/process.py":
        "tier 2 — spawns each agent-CLI turn in its own process group so a wedged turn "
        "can be killed as a tree. Windows has no process groups to kill.",
    "workhorse/workhorse/stack.py":
        "tier 2 — owns a long-lived dev stack across nodes; bringing one up detached and "
        "reaping it later is killpg by construction.",
    "workhorse/workhorse/config_run.py":
        "tier 2 — names SIGKILL as the watchdog's last resort for the turn supervisor above.",
    "groom/groom/alerts.py":
        "tier 2 — reports how a watched run died, which includes the signal that killed it.",
    "workflows/src/workhorse_workflows/okf_builder/walkthrough_web/nodes/stack.py":
        "tier 2 — the walkthrough's browser/server stack, same lifecycle as workhorse.stack.",
    "ostler/ostler/qa/session.py":
        "tier 2 — QA daemons are spawned detached and torn down by group; this is the "
        "module whose Linux/macOS killpg difference the portability skill uses as its example.",
    "ostler/ostler/qa/drivers.py":
        "tier 2 — runs one scenario per subprocess in its own group, so a scenario that "
        "wedges is killed as a tree and cannot leave a browser or a server behind. Same "
        "lifecycle as session.py above, on the executing side of it.",
    "ostler/ostler/qa/sandbox.py":
        "tier 3 — the sandbox drives Linux containers, so its /tmp paths name locations "
        "*inside* the image (the tmpfs home, the X socket dir) whatever the host is, and "
        "getuid/getgid map the invoking user into `docker run --user` so bind-mounted "
        "artifacts stay deletable — a mapping only the Linux docker daemon needs.",
}


def _rel(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _tier1_modules() -> list[Path]:
    modules: list[Path] = []
    for root in TIER1_SOURCE:
        base = REPO / root
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


def check_portability() -> list[str]:
    problems: list[str] = []
    scanned = 0
    for path in _tier1_modules():
        rel = _rel(path)
        if rel in ALLOWED:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue  # ruff owns syntax; this pass owns portability
        scanned += 1
        problems.extend(_findings(tree, rel))

    if not problems:
        print(
            f"ok: no POSIX-only API in {scanned} shipped modules "
            f"({len(ALLOWED)} declared process-supervision sites)"
        )
    return problems


def main() -> int:
    problems = check_portability()
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
    if ALLOWED:
        print("\nAlready declared:", file=sys.stderr)
        for path, why in sorted(ALLOWED.items()):
            print(f"  {path} — {why}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
