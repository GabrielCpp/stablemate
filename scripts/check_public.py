#!/usr/bin/env python3
"""Guard the public/private split."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "base-library"

BASE_SKILL_FAMILIES = {
    "farrier",
    "ostler",
    "groom",
    "workhorse",
    "architecture",
    "testing",
    "ui",
    "code-review",
    "grill",
    "brainstorm",
    "diagnosing-bugs",
    "root-cause",
    "vet-proposal",
    "vertical-slicing",
}
RESOLVER = REPO / "scripts" / "private_names.py"
HOOK_NAME = "hooks/pre-commit"

HOOK_MARKERS = ("scripts/check_public.py", "make farrier-run-hook")

BINARY_SNIFF_BYTES = 8000



def _text_of(path: Path) -> str | None:
    """The file's text, or None if it reads as binary or cannot be opened."""
    try:
        with path.open("rb") as handle:
            head = handle.read(BINARY_SNIFF_BYTES)
            if b"\0" in head:
                return None
            return (head + handle.read()).decode("utf-8", errors="replace")
    except OSError:
        return None


def _private_names_module():
    spec = importlib.util.spec_from_file_location("private_names", RESOLVER)
    assert spec and spec.loader, f"cannot load the name resolver at {RESOLVER}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tracked_files() -> list[Path]:
    """Files git tracks."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO / p for p in out.split("\0") if p]


def check_no_private_names() -> list[str]:
    """No private overlay name in any tracked path or file."""
    private_names = _private_names_module()
    pattern = private_names.pattern(private_names.load())
    if pattern is None:
        print(
            f"skip: no private names configured (${private_names.ENV_VAR} or "
            f"$GIT_DIR/{private_names.GIT_FILE}) — nothing to check against"
        )
        return []

    offenders: list[str] = []
    scanned = 0
    for path in _tracked_files():
        rel = path.relative_to(REPO).as_posix()
        if pattern.search(rel):
            offenders.append(f"{rel}: (in the path)")
            continue
        text = _text_of(path) if path.is_file() else None
        if text is None:
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()}")
    if not offenders:
        print(f"ok: no private project names in {scanned} tracked text files")
    return offenders


def check_no_private_names_in_history(
    repo: Path = REPO, waived: dict[str, dict[str, str]] | None = None
) -> list[str]:
    """No private name anywhere reachable from any ref — messages, paths, blobs."""
    private_names = _private_names_module()
    pattern = private_names.pattern(private_names.load())
    if pattern is None:
        return []

    waivers = private_names.load_waivers()["commit_messages"] if waived is None else waived

    offenders: list[str] = []

    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--all", "-z", "--format=%H%n%B"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    still_offending: set[str] = set()
    for record in log.split("\0"):
        if not record:
            continue
        sha, _, message = record.partition("\n")
        if pattern.search(message):
            if sha in waivers:
                still_offending.add(sha)
            else:
                offenders.append(f"commit {sha[:12]}: (in the commit message)")
    for sha in sorted(set(waivers) - still_offending):
        offenders.append(
            f"commit {sha[:12]}: stale waiver in $GIT_DIR/{private_names.WAIVER_FILE} — the commit is "
            "unreachable or its message is clean now; delete the entry"
        )

    listing = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--all", "--objects"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    candidates: dict[str, str] = {}
    flagged_paths: set[str] = set()
    for line in listing.splitlines():
        sha, _, path = line.partition(" ")
        if not path:
            continue
        if pattern.search(path) and path not in flagged_paths:
            flagged_paths.add(path)
            offenders.append(f"history path {path!r}: (in the path)")
        candidates.setdefault(sha, path)

    with subprocess.Popen(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    ) as proc:
        stdin, stdout = proc.stdin, proc.stdout
        assert stdin is not None and stdout is not None

        def _feed() -> None:
            for sha in candidates:
                stdin.write(sha.encode() + b"\n")
            stdin.close()

        feeder = threading.Thread(target=_feed)
        feeder.start()
        scanned = 0
        while True:
            header = stdout.readline()
            if not header:
                break
            sha, kind, size_text = header.decode().split()
            size = int(size_text)
            body = stdout.read(size)
            stdout.read(1)
            if kind != "blob":
                continue
            if b"\0" in body[:BINARY_SNIFF_BYTES]:
                continue
            scanned += 1
            text = body.decode("utf-8", errors="replace")
            if pattern.search(text):
                where = subprocess.run(
                    [
                        "git", "-C", str(repo), "log", "--all", "-1",
                        f"--find-object={sha}", "--format=%h",
                    ],
                    capture_output=True,
                    text=True,
                ).stdout.strip()
                offenders.append(
                    f"blob {sha[:12]} at {candidates[sha]!r} (e.g. commit {where}): "
                    "(in historical content)"
                )
        feeder.join()

    if not offenders:
        print(
            f"ok: no private project names in {scanned} historical blobs across all refs"
            f" ({len(waivers)} waived commit message(s))"
        )
    else:
        offenders.append(
            "history offenders need a rewrite (git filter-repo --replace-text), "
            "not a removal commit — removal is what made this class invisible"
        )
    return offenders


def check_no_private_names_in_commit_message(path: Path) -> list[str]:
    """No private name in a proposed commit message."""
    private_names = _private_names_module()
    pattern = private_names.pattern(private_names.load())
    if pattern is None:
        return []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    body = "\n".join(
        line for line in text.splitlines() if line.strip() and not line.startswith("#")
    )
    if not body.strip():
        return []

    offenders: list[str] = []
    for number, line in enumerate(body.splitlines(), start=1):
        if pattern.search(line):
            offenders.append(f"{path}:{number}: {line.strip()}")
    if not offenders:
        print(f"ok: no private project names in {path}")
    return offenders


def _installed_hook() -> Path:
    """The pre-commit hook git would run here, asked of git rather than assembled."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--git-path", HOOK_NAME],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return REPO / ".git" / HOOK_NAME
    path = Path(out)
    return path if path.is_absolute() else REPO / path


def check_hooks_installed() -> list[str]:
    """The guard has to be plugged in, and git does not plug it in for you."""
    private_names = _private_names_module()
    if not private_names.load():
        return []
    installed = _installed_hook()
    text = installed.read_text(encoding="utf-8", errors="replace") if installed.is_file() else ""
    missing = [marker for marker in HOOK_MARKERS if marker not in text]
    if missing:
        detail = "absent" if not text else "missing " + ", ".join(repr(m) for m in missing)
        return [
            f"{installed} is {detail} — the private-name, commit-message and "
            "generated-file guards are not running on this clone. Fix: make hooks"
        ]
    print(f"ok: git hooks resolve through {installed}")
    return []


def _isolate_from_the_overlay(install, config, discovery, base_cache) -> list[str]:
    """Resolve as a public user would: base only, no overlay in env or home config."""
    os.environ.pop("FARRIER_LIBRARY_DIR", None)
    os.environ[config.CONFIG_PATH_ENV] = str(Path(tempfile.mkdtemp()) / "config.toml")
    os.environ[discovery.BASE_DIR_ENV] = str(BASE)
    os.environ[base_cache.FETCH_ENV] = "0"
    install.set_layers(None)
    if [layer.name for layer in install.LAYERS] != [install.BASE_LAYER_NAME]:
        return ["the base library is not the only layer — the check would mean nothing"]
    return []


def check_base_stands_alone() -> list[str]:
    """Nothing in the base may depend on the private overlay."""
    from farrier import install
    from stablemate_core import base_cache, config, discovery

    if not install.is_library_dir(BASE):
        return [f"{BASE} is not a usable library root"]

    problems = _isolate_from_the_overlay(install, config, discovery, base_cache)
    if problems:
        return problems

    skills = install.load_layered_sources("skill", "library", "skills")
    if not skills:
        return ["the base library resolves no skills at all"]
    for skill in skills:
        if skill.layer is None or skill.layer.name != install.BASE_LAYER_NAME:
            problems.append(f"skill {skill.id!r} did not resolve from the base layer")
        family = skill.id.split("/", 1)[0]
        if family not in BASE_SKILL_FAMILIES:
            problems.append(
                f"skill {skill.id!r} is in the base but not in a base family "
                f"({', '.join(sorted(BASE_SKILL_FAMILIES))}) — the base carries the "
                "toolchain's own skills plus the generic cross-language contracts; "
                "stack mechanics and house rules are overlay content"
            )

    if not problems:
        print(f"ok: {len(skills)} base skills resolve with no overlay configured")
    return problems


def main(argv: list[str]) -> int:
    valid_flags = ("--names-only", "--history", "--commit-message")

    msg_path: Path | None = None
    if "--commit-message" in argv:
        i = argv.index("--commit-message")
        if i + 1 >= len(argv):
            print("--commit-message requires a path argument", file=sys.stderr)
            return 2
        msg_path = Path(argv[i + 1])
        unknown = [a for j, a in enumerate(argv) if a not in valid_flags
                   and not a.startswith("--commit-message=")
                   and not (j == i + 1)]
    elif any(a.startswith("--commit-message=") for a in argv):
        msg_path = Path(next(a for a in argv if a.startswith("--commit-message=")).split("=", 1)[1])
        unknown = [a for a in argv if a not in valid_flags and not a.startswith("--commit-message=")]
    else:
        unknown = [a for a in argv if a not in valid_flags]

    if unknown:
        print(
            f"usage: check_public.py [--names-only | --history | --commit-message <path>]  "
            f"(got {unknown})",
            file=sys.stderr,
        )
        return 2

    if "--names-only" in argv:
        checks = (check_no_private_names,)
    elif "--history" in argv:
        checks = (check_no_private_names_in_history,)
    elif msg_path is not None:
        checks = (lambda p=msg_path: check_no_private_names_in_commit_message(p),)
    else:
        checks = (
            check_no_private_names,
            check_no_private_names_in_history,
            check_hooks_installed,
            check_base_stands_alone,
        )

    failures = 0
    for check in checks:
        problems = check()
        if problems:
            failures += 1
            print(f"\nFAIL {check.__name__}:", file=sys.stderr)
            for p in problems:
                print(f"  {p}", file=sys.stderr)
    if failures:
        if "--names-only" in argv:
            print(
                "\nstablemate is public: replace these with neutral placeholders\n"
                "(acme, globex, api-service, web-app, mobile-app, example.com).\n"
                "To commit anyway: git commit --no-verify",
                file=sys.stderr,
            )
        if msg_path is not None:
            print(
                "\nstablemate is public: the proposed commit message carries a "
                "private overlay name. Replace it with a neutral reference\n"
                "(acme, globex, api-service, web-app, mobile-app, example.com).\n"
                "To commit anyway: git commit --no-verify",
                file=sys.stderr,
            )
        return 1
    if "--names-only" not in argv and msg_path is None:
        print("\nthe public/private split holds")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
